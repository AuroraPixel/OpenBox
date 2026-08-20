import argparse
import asyncio
import fcntl
import json
import os
import platform
import pty
import select
import shutil
import signal
import struct
import termios
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import subprocess

import psutil
import yaml
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, WebSocket, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import uvicorn

# --- 启动时间记录 ---
START_TIME = time.time()

# --- Models ---
class ExecuteRequest(BaseModel):
    command: str
    timeout: int = 120       # max timeout (absolute safety cap), default 2 minutes
    idle_timeout: int = 60   # seconds without output before emitting idle event
    workdir: str | None = None

class KillRequest(BaseModel):
    pid: int

class ExecuteResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str

class ListFilesRequest(BaseModel):
    path: str = "/workspace"

class WriteFileRequest(BaseModel):
    path: str
    content: str

class ReadFileRequest(BaseModel):
    path: str
    offset: int = 0  # 0-based line offset
    limit: int = 2000  # max lines to return

class GlobRequest(BaseModel):
    pattern: str
    path: str = "/workspace"

class GrepRequest(BaseModel):
    pattern: str
    path: str = "/workspace"
    type: str | None = None  # file type filter, e.g. "py", "js"
    max_results: int = 100

# --- API Key ---
SESSION_API_KEY = os.environ.get("SESSION_API_KEY", "")

# --- Protected command detection ---
# The action_server is the ONLY communication channel between the backend and the
# container. If it gets killed, all subsequent tool calls fail with 503. These
# patterns detect commands that would damage this communication channel.
import re as _re

ACTION_SERVER_PORT = int(os.environ.get("PORT", "8000"))

_PROTECTED_PATTERNS: list[tuple[str, str]] = [
    # kill PID 1 (init/tini) or -1 (all processes)
    (r'\bkill\b[^|;]*\s+(-\w+\s+)*1\b', "Cannot kill PID 1 (container init)"),
    (r'\bkill\b[^|;]*\s+-1\b', "Cannot signal all processes"),
    # pkill/killall targeting action_server runtime
    (r'\b(pkill|killall)\b[^|;]*\b(python[23]?|uvicorn|action_server)\b',
     "Cannot kill python/uvicorn/action_server — this would destroy the execution interface"),
    # fuser -k on port 8000
    (r'\bfuser\b[^|;]*-k[^|;]*\b8000\b',
     f"Cannot kill processes on port {ACTION_SERVER_PORT}"),
    (r'\bfuser\b[^|;]*\b8000\b[^|;]*-k',
     f"Cannot kill processes on port {ACTION_SERVER_PORT}"),
    # lsof piped to kill for port 8000
    (r'\blsof\b[^|]*\b8000\b.*\|\s*(xargs\s+)?kill',
     f"Cannot kill processes on port {ACTION_SERVER_PORT}"),
    # iptables/ufw blocking port 8000
    (r'\biptables\b[^|;]*(DROP|REJECT)[^|;]*\b8000\b',
     f"Cannot block port {ACTION_SERVER_PORT} with iptables"),
    (r'\bufw\b[^|;]*(deny|reject)[^|;]*\b8000\b',
     f"Cannot block port {ACTION_SERVER_PORT} with ufw"),
    # Modify/delete action_server files
    (r'\b(rm|mv|chmod|chown|truncate)\b[^|;]*/opt/action_server',
     "Cannot modify /opt/action_server — it contains the execution interface"),
    # System halt
    (r'\b(shutdown|poweroff|halt)\b', "Cannot shut down the container"),
    (r'\binit\s+[06]\b', "Cannot change runlevel"),
]

def _is_protected_command(command: str) -> str | None:
    """Return error message if command would damage the action_server, None if safe."""
    for pattern, msg in _PROTECTED_PATTERNS:
        if _re.search(pattern, command, _re.IGNORECASE):
            return msg
    return None

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # /workspace/skills → /data/skills/ convenience symlink for agent scripts
    skills_link = Path("/workspace/skills")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    if not skills_link.exists():
        try:
            skills_link.symlink_to(SKILLS_DIR)
        except OSError:
            pass
    # Create name-based symlinks for user-installed skills (skill packs, etc.)
    _ensure_skill_symlinks()
    yield

app = FastAPI(title="OpenBox Sandbox Action Server", lifespan=lifespan)

# --- API Key 中间件 ---
@app.middleware("http")
async def authenticate(request: Request, call_next):
    if request.url.path in ("/alive", "/docs", "/openapi.json", "/terminal"):
        return await call_next(request)
    api_key = request.headers.get("X-API-Key", "")
    if SESSION_API_KEY and api_key != SESSION_API_KEY:
        return JSONResponse(status_code=403, content={"detail": "Invalid API Key"})
    return await call_next(request)

# --- 健康检查 ---
@app.get("/alive")
async def alive():
    return {
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 2),
        "hostname": platform.node(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# --- Helper: kill entire process group ---
def _kill_process_tree(process):
    """Kill the process and its entire process group (children, grandchildren, etc.)."""
    try:
        pgid = os.getpgid(process.pid)
    except (OSError, ProcessLookupError):
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def _kill_process_tree_by_pid(pid: int):
    """Kill a process group by PID (for external kill requests)."""
    try:
        pgid = os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


# --- Kill endpoint ---
@app.post("/kill")
async def kill_command(req: KillRequest):
    """Kill a running command by PID."""
    protected_pids = {1, os.getpid(), os.getppid()}
    if req.pid in protected_pids:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot kill PID {req.pid} — it is a protected system process",
        )
    _kill_process_tree_by_pid(req.pid)
    return {"ok": True}


# --- 执行命令 ---
@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    blocked = _is_protected_command(req.command)
    if blocked:
        return ExecuteResponse(exit_code=1, stdout="", stderr=f"[BLOCKED] {blocked}")
    workdir = req.workdir or "/workspace"
    try:
        process = await asyncio.create_subprocess_shell(
            req.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=req.timeout
            )
        except asyncio.TimeoutError:
            _kill_process_tree(process)
            try:
                await asyncio.wait_for(process.communicate(), timeout=2)
            except asyncio.TimeoutError:
                pass
            return ExecuteResponse(exit_code=-1, stdout="", stderr=f"Command timed out after {req.timeout}s")
        return ExecuteResponse(
            exit_code=process.returncode or 0,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 上传文件 ---
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), destination: str = Form("/workspace")):
    dest_path = Path(destination)
    dest_path.mkdir(parents=True, exist_ok=True)
    file_path = dest_path / file.filename
    try:
        content = await file.read()
        file_path.write_bytes(content)
        return {"message": "File uploaded", "path": str(file_path), "size": len(content)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 下载文件 ---
@app.get("/download")
async def download_file(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if file_path.is_file():
        return StreamingResponse(
            open(file_path, "rb"),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{file_path.name}"'},
        )
    # 目录则打包为 zip
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in file_path.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(file_path))
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{file_path.name}.zip"'},
    )

# --- 列出文件 ---
@app.post("/list_files")
async def list_files(req: ListFilesRequest):
    target = Path(req.path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")
    entries = []
    for item in sorted(target.iterdir()):
        try:
            stat = item.stat()
            entries.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size": stat.st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        except PermissionError:
            entries.append({"name": item.name, "is_dir": item.is_dir(), "size": None, "modified": None})
    return {"path": req.path, "entries": entries}

# --- 系统信息 ---
@app.get("/system_info")
async def system_info():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu": {"percent": cpu_percent, "count": psutil.cpu_count()},
        "memory": {"total": memory.total, "used": memory.used, "percent": memory.percent},
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
        "hostname": platform.node(),
        "platform": platform.platform(),
    }

# --- Write File ---
@app.post("/write_file")
async def write_file(req: WriteFileRequest):
    """Write content to a file. Creates parent directories if needed."""
    file_path = Path(req.path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(req.content, encoding="utf-8")
    return {"message": "File written", "path": str(file_path), "size": len(req.content)}

# --- Read File ---
@app.post("/read_file")
async def read_file(req: ReadFileRequest):
    """Read file content with line numbers (cat -n format)."""
    file_path = Path(req.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.path}")
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"Not a file: {req.path}")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.split("\n")
    total_lines = len(lines)

    # Apply offset and limit
    start = max(0, req.offset)
    end = min(total_lines, start + req.limit)
    selected = lines[start:end]

    # Format with line numbers (cat -n style)
    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        # Truncate very long lines
        if len(line) > 2000:
            line = line[:2000] + "... (truncated)"
        numbered.append(f"     {i}\t{line}")

    return {
        "content": "\n".join(numbered),
        "total_lines": total_lines,
        "start_line": start + 1,
        "end_line": end,
        "path": req.path,
    }

# --- Glob ---
@app.post("/glob")
async def glob_files(req: GlobRequest):
    """Find files matching a glob pattern, sorted by modification time (newest first)."""
    base = Path(req.path)
    if not base.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {req.path}")

    matches = []
    try:
        for p in base.glob(req.pattern):
            if p.is_file():
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    mtime = 0
                matches.append((str(p), mtime))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid glob pattern: {e}")

    # Sort by modification time, newest first, limit to 1000
    matches.sort(key=lambda x: x[1], reverse=True)
    files = [m[0] for m in matches[:1000]]

    return {"files": files, "total": len(matches), "truncated": len(matches) > 1000}

# --- Grep ---
@app.post("/grep")
async def grep_files(req: GrepRequest):
    """Search file contents using grep."""
    cmd_parts = ["grep", "-rn", "--color=never"]

    # Add file type filter
    if req.type:
        ext_map = {
            "py": "*.py", "js": "*.js", "ts": "*.ts", "tsx": "*.tsx",
            "jsx": "*.jsx", "go": "*.go", "rs": "*.rs", "java": "*.java",
            "c": "*.c", "cpp": "*.cpp", "h": "*.h", "rb": "*.rb",
            "php": "*.php", "css": "*.css", "html": "*.html", "md": "*.md",
            "json": "*.json", "yaml": "*.yaml", "yml": "*.yml",
            "toml": "*.toml", "xml": "*.xml", "sh": "*.sh",
            "sql": "*.sql", "vue": "*.vue", "svelte": "*.svelte",
        }
        glob_pattern = ext_map.get(req.type, f"*.{req.type}")
        cmd_parts.extend(["--include", glob_pattern])

    cmd_parts.extend(["-m", str(req.max_results), "--", req.pattern, req.path])

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace")

        return {
            "output": output,
            "exit_code": process.returncode or 0,
            "error": stderr.decode("utf-8", errors="replace") if stderr else "",
        }
    except asyncio.TimeoutError:
        return {"output": "", "exit_code": -1, "error": "grep timed out after 30s"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Execute Stream (SSE) ---
@app.post("/execute_stream")
async def execute_stream(req: ExecuteRequest):
    """Execute a command with streaming output via SSE."""
    blocked = _is_protected_command(req.command)
    if blocked:
        async def blocked_gen():
            yield {"event": "output", "data": json.dumps({
                "type": "system", "content": f"[BLOCKED] {blocked}\n",
            })}
            yield {"event": "exit", "data": json.dumps({
                "exit_code": 1, "timed_out": False,
            })}
        return EventSourceResponse(blocked_gen())
    workdir = req.workdir or "/workspace"

    async def event_generator():
        try:
            process = await asyncio.create_subprocess_shell(
                req.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                start_new_session=True,
            )
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
            return

        import json as json_mod

        # Emit started event with PID so the client can kill the process later
        yield {"event": "started", "data": json_mod.dumps({"pid": process.pid})}

        # Global timeout killer: runs in parallel with the reader.
        # If the process exceeds the timeout, kill it so the reader can finish.
        timeout_seconds = req.timeout or 120
        idle_timeout_seconds = req.idle_timeout or 30
        timed_out_flag = False
        start_time = time.time()

        async def _timeout_killer():
            nonlocal timed_out_flag
            await asyncio.sleep(timeout_seconds)
            if process.returncode is None:  # still running
                timed_out_flag = True
                _kill_process_tree(process)

        timeout_task = asyncio.create_task(_timeout_killer())

        # Read both streams concurrently, but also watch for process exit.
        # When the shell process exits, give remaining output a short grace
        # period then stop — background processes (nohup, &) keep pipes open
        # indefinitely and would block forever otherwise.
        stdout_done = False
        stderr_done = False
        process_exited = False

        async def reader():
            nonlocal stdout_done, stderr_done, process_exited
            tasks = {}
            wait_task = asyncio.create_task(process.wait())
            last_output_time = time.time()

            while not (stdout_done and stderr_done):
                if not stdout_done and "stdout" not in tasks:
                    tasks["stdout"] = asyncio.create_task(process.stdout.readline())
                if not stderr_done and "stderr" not in tasks:
                    tasks["stderr"] = asyncio.create_task(process.stderr.readline())

                if not tasks:
                    break

                # Also watch for process exit
                waitables = set(tasks.values())
                if not process_exited:
                    waitables.add(wait_task)

                done, _ = await asyncio.wait(
                    waitables,
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=idle_timeout_seconds,
                )

                # Idle detection: no output for idle_timeout seconds
                if not done:
                    idle_secs = int(time.time() - last_output_time)
                    total_secs = int(time.time() - start_time)
                    yield {"event": "idle", "data": json_mod.dumps({
                        "idle_seconds": idle_secs,
                        "total_seconds": total_secs,
                    })}
                    continue  # Go back to waiting, don't kill

                if wait_task in done:
                    process_exited = True

                for name in list(tasks.keys()):
                    if tasks[name] in done:
                        line = tasks.pop(name).result()
                        if not line:
                            if name == "stdout":
                                stdout_done = True
                            else:
                                stderr_done = True
                        else:
                            last_output_time = time.time()
                            yield {"event": "output", "data": json_mod.dumps({
                                "type": name,
                                "content": line.decode("utf-8", errors="replace"),
                            })}

                # If process exited, drain remaining output with a short timeout
                if process_exited and not (stdout_done and stderr_done):
                    remaining = {k: v for k, v in tasks.items() if v not in done}
                    if remaining:
                        try:
                            drain_done, drain_pending = await asyncio.wait(
                                remaining.values(), timeout=0.5
                            )
                            for name in list(remaining.keys()):
                                if remaining[name] in drain_done:
                                    line = remaining[name].result()
                                    if line:
                                        yield {"event": "output", "data": json_mod.dumps({
                                            "type": name,
                                            "content": line.decode("utf-8", errors="replace"),
                                        })}
                            for t in drain_pending:
                                t.cancel()
                        except Exception:
                            pass
                    break

            if not wait_task.done():
                wait_task.cancel()

        try:
            async for event in reader():
                yield event

            if not process_exited:
                exit_code = await asyncio.wait_for(process.wait(), timeout=5)
            else:
                exit_code = process.returncode or 0
        except asyncio.TimeoutError:
            _kill_process_tree(process)
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
            exit_code = -1
        finally:
            timeout_task.cancel()

        if timed_out_flag:
            exit_code = -1
            yield {"event": "output", "data": json.dumps({
                "type": "system",
                "content": f"Command terminated: timeout {timeout_seconds}s exceeded\n",
            })}

        yield {"event": "exit", "data": json.dumps({
            "exit_code": exit_code,
            "timed_out": exit_code == -1,
        })}

    return EventSourceResponse(event_generator())

# --- Listening Ports Detection ---
@app.get("/listening_ports")
async def listening_ports():
    """Detect TCP ports with services actively listening inside this container.

    Excludes the action server's own port and returns process info for each port.
    """
    result = []
    seen_ports = set()
    for conn in psutil.net_connections(kind="tcp"):
        # Only LISTEN state
        if conn.status != psutil.CONN_LISTEN:
            continue
        port = conn.laddr.port
        # Skip action server port and duplicates
        if port == ACTION_SERVER_PORT or port in seen_ports:
            continue
        # Only 0.0.0.0 or 127.0.0.1 bindings (not random ephemeral)
        if conn.laddr.ip not in ("0.0.0.0", "127.0.0.1", "::", "::1"):
            continue
        seen_ports.add(port)
        # Try to get process name
        proc_name = ""
        cmd = ""
        if conn.pid:
            try:
                p = psutil.Process(conn.pid)
                proc_name = p.name()
                cmd = " ".join(p.cmdline()[:5])  # first 5 args
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        result.append({
            "port": port,
            "pid": conn.pid,
            "process": proc_name,
            "command": cmd,
        })
    result.sort(key=lambda x: x["port"])
    return {"ports": result}


# --- Port Proxy (forward requests to user apps running inside container) ---
@app.api_route("/proxy/{port:int}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
@app.api_route("/proxy/{port:int}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_port(request: Request, port: int, path: str = ""):
    """Reverse-proxy requests to a user application running on the given port inside the container."""
    import httpx
    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "x-api-key", "connection")}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )
        # Forward the response back
        excluded_headers = {"transfer-encoding", "connection", "content-encoding"}
        response_headers = {k: v for k, v in resp.headers.items()
                           if k.lower() not in excluded_headers}
        from starlette.responses import Response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
            media_type=resp.headers.get("content-type"),
        )
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"detail": f"No service running on port {port}"})
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"detail": f"Timeout connecting to port {port}"})


# --- PTY Terminal WebSocket ---
def _blocking_read(fd: int, size: int = 4096) -> bytes | None:
    """Blocking read from file descriptor, used in executor.
    Returns data bytes, empty bytes on timeout, or None on fd error."""
    r, _, _ = select.select([fd], [], [], 0.5)
    if r:
        try:
            return os.read(fd, size)
        except OSError:
            return None
    return b""


@app.websocket("/terminal")
async def terminal_ws(ws: WebSocket, api_key: str = Query("")):
    # Authenticate via query parameter (WebSocket doesn't go through HTTP middleware)
    if SESSION_API_KEY and api_key != SESSION_API_KEY:
        await ws.accept()
        await ws.close(code=4003, reason="Invalid API Key")
        return

    await ws.accept()

    # Create PTY
    master_fd, slave_fd = pty.openpty()

    # Set initial terminal size (80x24)
    winsize = struct.pack("HHHH", 24, 80, 0, 0)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

    # Fork child process
    pid = os.fork()
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)

        # Redirect stdio to slave PTY
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)

        # Switch to sandbox user
        try:
            import pwd
            pw = pwd.getpwnam("sandbox")
            os.setgid(pw.pw_gid)
            os.setuid(pw.pw_uid)
            home = pw.pw_dir
        except (KeyError, PermissionError):
            home = os.environ.get("HOME", "/root")

        env = {
            "TERM": "xterm-256color",
            "HOME": home,
            "USER": os.environ.get("USER", "sandbox"),
            "LANG": "C.UTF-8",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "SHELL": "/bin/bash",
        }

        os.chdir("/workspace")
        os.execve("/bin/bash", ["bash", "--login"], env)

    # Parent process
    os.close(slave_fd)

    # Set master_fd to non-blocking
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_running_loop()

    async def read_pty_to_ws():
        """Read from PTY master and send to WebSocket."""
        try:
            while True:
                try:
                    data = await loop.run_in_executor(None, _blocking_read, master_fd)
                    if data is None:
                        break  # fd error, PTY closed
                    if data:
                        await ws.send_bytes(b"\x00" + data)
                    # empty bytes means select timeout, continue loop
                except OSError:
                    break
        except Exception:
            pass

    async def read_ws_to_pty():
        """Read from WebSocket and write to PTY master."""
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break

                if "bytes" in message and message["bytes"]:
                    raw = message["bytes"]
                    if len(raw) < 1:
                        continue
                    prefix = raw[0]
                    payload = raw[1:]

                    if prefix == 0x00:
                        os.write(master_fd, payload)
                    elif prefix == 0x01:
                        if len(payload) >= 4:
                            cols = (payload[0] << 8) | payload[1]
                            rows = (payload[2] << 8) | payload[3]
                            winsize = struct.pack("HHHH", rows, cols, 0, 0)
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            os.kill(pid, signal.SIGWINCH)
                elif "text" in message and message["text"]:
                    pass
        except Exception:
            pass

    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(read_pty_to_ws()), asyncio.create_task(read_ws_to_pty())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        await asyncio.sleep(0.1)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            await ws.close()
        except Exception:
            pass


# ============================================================
# Dev-Browser Relay Management
# ============================================================

_dev_browser_process: subprocess.Popen | None = None


def _is_dev_browser_running() -> bool:
    """Check if the dev-browser relay process is alive."""
    global _dev_browser_process
    if _dev_browser_process is None:
        return False
    if _dev_browser_process.poll() is not None:
        _dev_browser_process = None
        return False
    return True


@app.post("/dev-browser/start")
async def dev_browser_start():
    """Start the dev-browser relay server in the background."""
    global _dev_browser_process
    if _is_dev_browser_running():
        return {"status": "running", "pid": _dev_browser_process.pid}

    relay_dir = BUILTIN_SKILLS_DIR / "dev-browser"
    if not relay_dir.exists():
        raise HTTPException(status_code=500, detail="dev-browser not installed in container")

    try:
        _dev_browser_process = subprocess.Popen(
            ["npm", "run", "start-relay"],
            cwd=str(relay_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "HOST": "127.0.0.1", "PORT": "9222"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start relay: {e}")

    # Wait for port 9222 to become available (up to 5 seconds)
    import socket
    for _ in range(50):
        if _dev_browser_process.poll() is not None:
            _dev_browser_process = None
            raise HTTPException(status_code=500, detail="Relay process exited unexpectedly")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                s.connect(("127.0.0.1", 9222))
                return {"status": "running", "pid": _dev_browser_process.pid}
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.1)

    return {"status": "starting", "pid": _dev_browser_process.pid}


@app.post("/dev-browser/stop")
async def dev_browser_stop():
    """Stop the dev-browser relay server."""
    global _dev_browser_process
    if not _is_dev_browser_running():
        return {"status": "stopped"}

    try:
        _dev_browser_process.terminate()
        try:
            _dev_browser_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _dev_browser_process.kill()
    except Exception:
        pass
    _dev_browser_process = None
    return {"status": "stopped"}


@app.get("/dev-browser/status")
async def dev_browser_status():
    """Get dev-browser relay status and extension connection state."""
    if not _is_dev_browser_running():
        return {"status": "stopped", "extensionConnected": False}

    # Query the relay server for extension connection status
    import httpx
    extension_connected = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://127.0.0.1:9222/")
            if resp.status_code == 200:
                data = resp.json()
                extension_connected = data.get("extensionConnected", False)
    except Exception:
        pass

    return {
        "status": "running",
        "pid": _dev_browser_process.pid if _dev_browser_process else None,
        "extensionConnected": extension_connected,
    }


@app.websocket("/dev-browser/ws")
async def dev_browser_ws(ws: WebSocket, api_key: str = Query("")):
    """WebSocket proxy: forwards extension traffic to the relay server at localhost:9222."""
    # Authenticate
    if SESSION_API_KEY and api_key != SESSION_API_KEY:
        await ws.accept()
        await ws.close(code=4003, reason="Invalid API Key")
        return

    await ws.accept()

    import websockets

    relay_url = "ws://127.0.0.1:9222/extension"
    try:
        async with websockets.connect(relay_url, max_size=2**20) as relay_ws:

            async def client_to_relay():
                try:
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if "text" in message and message["text"]:
                            await relay_ws.send(message["text"])
                        elif "bytes" in message and message["bytes"]:
                            await relay_ws.send(message["bytes"])
                except Exception:
                    pass

            async def relay_to_client():
                try:
                    async for msg in relay_ws:
                        if isinstance(msg, str):
                            await ws.send_text(msg)
                        else:
                            await ws.send_bytes(msg)
                except Exception:
                    pass

            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(client_to_relay()),
                    asyncio.create_task(relay_to_client()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

    except Exception as e:
        try:
            await ws.send_json({"type": "error", "data": f"Failed to connect to relay: {e}"})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ============================================================
# Skill Management
# ============================================================

SKILLS_DIR = Path("/data/skills")            # User-installed skills (bind-mounted, persistent)
BUILTIN_SKILLS_DIR = Path("/opt/openbox/skills")  # System built-in skills (baked into image)


class InstallSkillRequest(BaseModel):
    url: str | None = None
    name: str | None = None
    content: str | None = None


def _parse_skill_frontmatter(md_content: str) -> dict:
    """Parse YAML frontmatter from a SKILL.md file."""
    md_content = md_content.strip()
    if not md_content.startswith("---"):
        return {"name": "", "description": ""}
    parts = md_content.split("---", 2)
    if len(parts) < 3:
        return {"name": "", "description": ""}
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}
    return {
        "name": meta.get("name", ""),
        "description": meta.get("description", ""),
    }


def _ensure_skill_symlinks() -> None:
    """Create name-based symlinks for skills whose frontmatter name differs from the install directory.

    For example, if a skill is installed at /data/skills/ui-ux-pro-max-skill/
    but the SKILL.md name is "ui-ux-pro-max", create:
      /data/skills/ui-ux-pro-max -> /data/skills/ui-ux-pro-max-skill/.claude/skills/ui-ux-pro-max/

    This makes paths like "skills/ui-ux-pro-max/scripts/search.py" work from /workspace/.
    """
    if not SKILLS_DIR.exists():
        return
    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        for skill_md in _find_skill_mds(skill_dir):
            skill_data_dir = skill_md.parent
            meta = _parse_skill_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
            skill_name = meta.get("name") or skill_data_dir.name
            # If the name differs from the install dir, create a convenience symlink
            if skill_name != skill_dir.name:
                link_path = SKILLS_DIR / skill_name
                if not link_path.exists():
                    try:
                        link_path.symlink_to(skill_data_dir)
                    except OSError:
                        pass


# Directories and files that are never worth listing to the model or shipping
# over the tunnel. dev-browser alone carries ~890 node_modules entries, which
# crowded the genuinely useful files (scripts/, references/) out of a 50-line
# listing and made GET /skills a 55KB response on every agent step.
_SKILL_FILE_SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv",
                         "venv", "dist", "build", ".next", ".cache"}
_SKILL_FILE_LIST_LIMIT = 20    # /skills — the UI shows three and a count
_SKILL_FILE_DETAIL_LIMIT = 50  # /skills/{name} — what the model sees


def _skill_files(skill_data_dir, limit: int = _SKILL_FILE_DETAIL_LIMIT) -> list:
    """Files bundled with a skill, minus the noise.

    SKILL.md is excluded because its content is inlined right above the
    listing. Dotfiles and macOS AppleDouble stubs (._foo, created when a skill
    is zipped on a Mac) are excluded because they are not addressable content.
    """
    out = []
    try:
        for f in sorted(skill_data_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(skill_data_dir)
            parts = rel.parts
            if any(p in _SKILL_FILE_SKIP_DIRS for p in parts):
                continue
            if any(p.startswith(".") or p.startswith("._") for p in parts):
                continue
            if rel.name == "SKILL.md":
                continue
            out.append(str(rel))
            if len(out) >= limit:
                break
    except OSError:
        pass
    return out


def _find_skill_mds(skill_dir: Path) -> list[Path]:
    """Find all SKILL.md files in a skill directory.

    Supports three layouts:
    1. Simple: {skill_dir}/SKILL.md
    2. Claude Code plugin: {skill_dir}/.claude/skills/*/SKILL.md
    3. Skills collection: {skill_dir}/skills/*/SKILL.md
    """
    results = []
    # Simple layout
    simple = skill_dir / "SKILL.md"
    if simple.exists():
        results.append(simple)
    # Claude Code plugin layout
    claude_skills = skill_dir / ".claude" / "skills"
    if claude_skills.is_dir():
        for sub in sorted(claude_skills.iterdir()):
            md = sub / "SKILL.md"
            if sub.is_dir() and md.exists():
                results.append(md)
    # Skills collection layout: skills/*/SKILL.md
    skills_dir = skill_dir / "skills"
    if skills_dir.is_dir():
        for sub in sorted(skills_dir.iterdir()):
            md = sub / "SKILL.md"
            if sub.is_dir() and md.exists():
                results.append(md)
    return results


def _scan_skills_in_dir(skills_dir: Path, source: str) -> list[dict]:
    """Scan a single directory for skills. Skips symlinks to avoid duplicates."""
    skills = []
    if not skills_dir.exists():
        return skills
    for skill_dir in sorted(skills_dir.iterdir()):
        # Skip symlinks (they are aliases created by _ensure_skill_symlinks,
        # the real skills are found via _find_skill_mds on actual directories)
        if not skill_dir.is_dir() or skill_dir.is_symlink():
            continue
        skill_mds = _find_skill_mds(skill_dir)
        if not skill_mds:
            continue
        for skill_md in skill_mds:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            meta = _parse_skill_frontmatter(content)
            skill_data_dir = skill_md.parent
            files = _skill_files(skill_data_dir, _SKILL_FILE_LIST_LIMIT)
            skills.append({
                "name": meta.get("name") or skill_data_dir.name,
                "description": meta.get("description", ""),
                "source": source,
                "content": content,
                "files": files,
                "install_dir": skill_dir.name,
                "base_dir": str(skill_data_dir),
            })
    return skills


def _scan_skills() -> list[dict]:
    """Scan both system and user skill directories.

    System skills (/opt/openbox/skills/) are baked into the image, source="builtin".
    User skills (/data/skills/) are installed by the user, source="container".
    If same name exists in both, user version takes precedence.
    """
    builtin = _scan_skills_in_dir(BUILTIN_SKILLS_DIR, source="builtin")
    user = _scan_skills_in_dir(SKILLS_DIR, source="container")

    # Merge: user skills take precedence over builtin with same name
    seen_names = set()
    merged = []
    for skill in user:
        seen_names.add(skill["name"])
        merged.append(skill)
    for skill in builtin:
        if skill["name"] not in seen_names:
            merged.append(skill)
    return merged


@app.get("/skills")
async def list_skills():
    """List all installed skills (builtin + user)."""
    return _scan_skills()


@app.get("/skills/{name}")
async def get_skill(name: str):
    """Get a specific skill by name."""
    all_skills = _scan_skills()
    for skill in all_skills:
        if skill["name"] == name or skill.get("install_dir") == name:
            return skill
    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


@app.post("/skills/install")
async def install_skill(req: InstallSkillRequest):
    """Install a skill from URL (git clone) or from pasted content."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if req.url:
        # Determine name from URL or explicit name
        skill_name = req.name
        if not skill_name:
            # Extract name from git URL: https://github.com/user/repo.git -> repo
            url_path = req.url.rstrip("/").rstrip(".git")
            skill_name = url_path.split("/")[-1] or "unnamed-skill"
        target = SKILLS_DIR / skill_name
        if target.exists():
            shutil.rmtree(target)
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", req.url, str(target)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"git clone failed: {result.stderr.strip()}",
                )
            # Remove .git directory to save space
            git_dir = target / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)
        except subprocess.TimeoutExpired:
            if target.exists():
                shutil.rmtree(target)
            raise HTTPException(status_code=504, detail="git clone timed out")
    elif req.content:
        skill_name = req.name
        if not skill_name:
            # Try to extract name from frontmatter
            meta = _parse_skill_frontmatter(req.content)
            skill_name = meta.get("name") or "unnamed-skill"
        target = SKILLS_DIR / skill_name
        target.mkdir(parents=True, exist_ok=True)
        (target / "SKILL.md").write_text(req.content, encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail="Provide either 'url' or 'content'")

    # Create name-based symlinks so skill paths work from /workspace/
    _ensure_skill_symlinks()

    # Read back and return the installed skill(s)
    skill_mds = _find_skill_mds(target)
    if not skill_mds:
        raise HTTPException(status_code=400, detail="No SKILL.md found after install")
    # Return the first skill found (most repos have one)
    skill_md = skill_mds[0]
    content = skill_md.read_text(encoding="utf-8", errors="replace")
    meta = _parse_skill_frontmatter(content)
    skill_data_dir = skill_md.parent
    files = _skill_files(skill_data_dir)
    return {
        "name": meta.get("name") or skill_name,
        "description": meta.get("description", ""),
        "source": "container",
        "content": content,
        "files": files,
        "install_dir": skill_name,
        "base_dir": str(skill_data_dir),
    }


@app.post("/skills/upload")
async def upload_skill_archive(file: UploadFile = File(...), name: str = Form("")):
    """Install a skill from an uploaded archive (zip/tar/tar.gz/tgz/rar).

    Extracts the archive, validates it contains SKILL.md in a standard layout,
    and installs to /data/skills/{name}/.
    """
    import zipfile
    import tarfile

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "archive"
    ext = filename.lower()

    # Determine archive type
    if ext.endswith(".zip"):
        archive_type = "zip"
    elif ext.endswith((".tar.gz", ".tgz")):
        archive_type = "tar.gz"
    elif ext.endswith(".tar"):
        archive_type = "tar"
    elif ext.endswith(".rar"):
        archive_type = "rar"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported archive format: {filename}. Use zip, tar, tar.gz, tgz, or rar.")

    # Read file content
    content_bytes = await file.read()
    if len(content_bytes) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="Archive too large (max 50MB)")

    # Determine skill name
    skill_name = name.strip() if name.strip() else filename.rsplit(".", 1)[0]
    # Clean up double extensions like .tar.gz
    for suffix in (".tar", ".tgz"):
        if skill_name.endswith(suffix):
            skill_name = skill_name[:-len(suffix)]
    skill_name = skill_name.replace(" ", "-")

    # Extract to temp dir first for validation
    tmp_dir = Path(f"/tmp/skill_upload_{skill_name}_{os.getpid()}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    try:
        # Extract archive
        if archive_type == "zip":
            import io
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                # Security: check for path traversal
                for member in zf.namelist():
                    if ".." in member or member.startswith("/"):
                        raise HTTPException(status_code=400, detail=f"Unsafe path in archive: {member}")
                zf.extractall(tmp_dir)

        elif archive_type in ("tar", "tar.gz"):
            import io
            mode = "r:gz" if archive_type == "tar.gz" else "r:"
            with tarfile.open(fileobj=io.BytesIO(content_bytes), mode=mode) as tf:
                # Security: check for path traversal
                for member in tf.getmembers():
                    if ".." in member.name or member.name.startswith("/"):
                        raise HTTPException(status_code=400, detail=f"Unsafe path in archive: {member.name}")
                tf.extractall(tmp_dir)

        elif archive_type == "rar":
            # Write to temp file for rarfile/unrar
            tmp_file = tmp_dir / "archive.rar"
            tmp_file.write_bytes(content_bytes)
            try:
                result = subprocess.run(
                    ["unrar", "x", "-y", str(tmp_file), str(tmp_dir) + "/"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    raise HTTPException(status_code=400, detail=f"RAR extraction failed: {result.stderr.strip()}")
            except FileNotFoundError:
                raise HTTPException(status_code=400, detail="RAR not supported: 'unrar' not installed in container")
            finally:
                tmp_file.unlink(missing_ok=True)

        # If archive extracted into a single subdirectory, use that as root
        entries = list(tmp_dir.iterdir())
        extract_root = tmp_dir
        if len(entries) == 1 and entries[0].is_dir():
            extract_root = entries[0]

        # Validate: must have SKILL.md in standard layout
        skill_mds = _find_skill_mds(extract_root)
        if not skill_mds:
            found_files = [str(f.relative_to(extract_root)) for f in extract_root.rglob("*") if f.is_file()][:20]
            raise HTTPException(
                status_code=400,
                detail=f"No SKILL.md found in archive. Expected SKILL.md at root, skills/*/SKILL.md, or .claude/skills/*/SKILL.md.\nFiles found: {', '.join(found_files)}",
            )

        # Validation passed — move to skills directory
        target = SKILLS_DIR / skill_name
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extract_root), str(target))

    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Run install.sh if present (for dependency setup)
    install_log = ""
    install_sh = target / "install.sh"
    if install_sh.exists():
        try:
            result = subprocess.run(
                ["bash", str(install_sh)],
                capture_output=True, text=True, timeout=120,
                cwd=str(target),
            )
            install_log = result.stdout + result.stderr
            if result.returncode != 0:
                install_log = f"install.sh exited with code {result.returncode}:\n{install_log}"
        except subprocess.TimeoutExpired:
            install_log = "install.sh timed out (120s)"
        except Exception as e:
            install_log = f"install.sh failed: {e}"

    # Create symlinks
    _ensure_skill_symlinks()

    # Read README if present
    readme = ""
    for readme_name in ("README.md", "readme.md", "README.txt"):
        readme_path = target / readme_name
        if readme_path.exists():
            readme = readme_path.read_text(encoding="utf-8", errors="replace")[:2000]
            break

    # Return all installed skills
    skill_mds = _find_skill_mds(target)
    all_skills = []
    for skill_md in skill_mds:
        md_content = skill_md.read_text(encoding="utf-8", errors="replace")
        meta = _parse_skill_frontmatter(md_content)
        skill_data_dir = skill_md.parent
        files = _skill_files(skill_data_dir)
        all_skills.append({
            "name": meta.get("name") or skill_md.parent.name,
            "description": meta.get("description", ""),
            "source": "container",
            "content": md_content,
            "files": files,
            "base_dir": str(skill_data_dir),
        })

    return {
        "name": skill_name,
        "skills": all_skills,
        "skills_count": len(all_skills),
        "install_dir": skill_name,
        "install_log": install_log,
        "readme": readme,
    }


@app.delete("/skills/{name}")
async def uninstall_skill(name: str):
    """Uninstall a user-installed skill. Builtin skills cannot be deleted."""
    # Check if it's a builtin skill — reject deletion
    builtin_skills = _scan_skills_in_dir(BUILTIN_SKILLS_DIR, source="builtin")
    for skill in builtin_skills:
        if skill["name"] == name or skill.get("install_dir") == name:
            raise HTTPException(status_code=403, detail=f"Cannot uninstall builtin skill '{name}'")

    # Direct match by directory name in user skills
    target = SKILLS_DIR / name
    if target.exists() and not target.is_symlink():
        shutil.rmtree(target)
        # Also remove any symlinks that pointed into this directory
        _cleanup_broken_symlinks()
        return {"ok": True, "message": f"Skill '{name}' uninstalled"}

    # If it's a symlink (alias), remove the symlink
    if target.is_symlink():
        target.unlink()
        return {"ok": True, "message": f"Skill alias '{name}' removed"}

    # Search by skill name (from frontmatter) in user skills only
    user_skills = _scan_skills_in_dir(SKILLS_DIR, source="container")
    for skill in user_skills:
        if skill["name"] == name:
            install_dir = skill.get("install_dir")
            if install_dir:
                t = SKILLS_DIR / install_dir
                if t.exists():
                    shutil.rmtree(t)
                    _cleanup_broken_symlinks()
                    return {"ok": True, "message": f"Skill '{name}' uninstalled"}
    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")


def _cleanup_broken_symlinks():
    """Remove broken symlinks in SKILLS_DIR after a skill directory is deleted."""
    if not SKILLS_DIR.exists():
        return
    for entry in SKILLS_DIR.iterdir():
        if entry.is_symlink() and not entry.exists():
            entry.unlink()


# ============================================================
# MCP Server Management
# ============================================================

MCP_CONFIG_PATH = Path("/data/mcp/config.json")


class AddMcpServerRequest(BaseModel):
    name: str
    type: str = "stdio"          # "stdio" or "remote"
    command: str | None = None   # for stdio
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None       # for remote
    headers: dict[str, str] | None = None  # Custom HTTP headers for remote
    timeout: int = 60                      # Per-server request timeout


class CallMcpToolRequest(BaseModel):
    arguments: dict = {}


class ReadMcpResourceRequest(BaseModel):
    server: str
    uri: str


class GetMcpPromptRequest(BaseModel):
    server: str
    name: str
    arguments: dict | None = None


class RawStreamableHttpSession:
    """Raw HTTP-based MCP client that bypasses the SDK's buggy streamablehttp_client.

    Implements MCP JSON-RPC over HTTP POST. The server responds with either:
    - Direct JSON (application/json) for simple request/response
    - SSE stream (text/event-stream) for streaming responses

    This works around a known issue where the SDK's session.initialize() hangs
    on servers like Tavily that use Streamable HTTP transport.
    """

    def __init__(self, url: str, headers: dict[str, str] | None = None, timeout: int = 60):
        self.url = url
        self._session_id: str | None = None
        self._request_id = 0
        self._server_info: dict = {}
        self._client: "httpx.AsyncClient | None" = None
        self._extra_headers = headers or {}
        self._timeout = timeout

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _ensure_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=float(self._timeout))

    async def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and return the result."""
        await self._ensure_client()

        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self._extra_headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        resp = await self._client.post(self.url, json=payload, headers=headers)
        resp.raise_for_status()

        # Store session ID from response
        if "mcp-session-id" in resp.headers:
            self._session_id = resp.headers["mcp-session-id"]

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response to extract JSON-RPC result
            return self._parse_sse_response(resp.text, req_id)
        else:
            # Direct JSON response
            data = resp.json()
            if "error" in data:
                raise Exception(f"MCP error: {data['error']}")
            return data.get("result", {})

    def _parse_sse_response(self, text: str, expected_id: int) -> dict:
        """Parse SSE text to find the JSON-RPC response matching our request ID."""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    if data.get("id") == expected_id:
                        if "error" in data:
                            raise Exception(f"MCP error: {data['error']}")
                        return data.get("result", {})
                except json.JSONDecodeError:
                    continue
        raise Exception("No matching JSON-RPC response found in SSE stream")

    async def _send_notification(self, method: str, params: dict | None = None):
        """Send a JSON-RPC notification (no id, no response expected)."""
        await self._ensure_client()

        payload = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        resp = await self._client.post(self.url, json=payload, headers=headers)
        # Notifications may return 200 or 204
        if resp.status_code not in (200, 202, 204):
            resp.raise_for_status()
        # Update session ID if present
        if "mcp-session-id" in resp.headers:
            self._session_id = resp.headers["mcp-session-id"]

    async def initialize(self):
        """Initialize the MCP session."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "openbox-container", "version": "1.0.0"},
        })
        self._server_info = result
        # Send initialized notification
        await self._send_notification("notifications/initialized")

    async def list_tools(self) -> list[dict]:
        """List available tools from the MCP server."""
        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call a tool on the MCP server."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        return result

    async def list_resources(self) -> list[dict]:
        """List available resources from the MCP server."""
        result = await self._send_request("resources/list", {})
        return result.get("resources", [])

    async def read_resource(self, uri: str) -> dict:
        """Read a specific resource by URI."""
        return await self._send_request("resources/read", {"uri": uri})

    async def list_prompts(self) -> list[dict]:
        """List available prompts from the MCP server."""
        result = await self._send_request("prompts/list", {})
        return result.get("prompts", [])

    async def get_prompt(self, name: str, arguments: dict | None = None) -> dict:
        """Get a specific prompt by name."""
        params: dict = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._send_request("prompts/get", params)

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class ContainerMcpManager:
    """Manages MCP server processes inside the container."""

    def __init__(self):
        self._servers: dict[str, dict] = {}  # name -> server state
        self._sessions: dict[str, object] = {}  # name -> ClientSession
        self._transports: dict[str, object] = {}  # name -> transport context manager
        self._tools: dict[str, list[dict]] = {}  # name -> list of tool dicts
        self._resources: dict[str, list[dict]] = {}  # name -> list of resource dicts
        self._prompts: dict[str, list[dict]] = {}  # name -> list of prompt dicts

    def _load_config(self) -> dict:
        """Load MCP config from persistent storage."""
        if MCP_CONFIG_PATH.exists():
            try:
                return json.loads(MCP_CONFIG_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"servers": {}}

    def _save_config(self, config: dict):
        """Save MCP config to persistent storage."""
        MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        MCP_CONFIG_PATH.write_text(json.dumps(config, indent=2))

    def list_servers(self) -> list[dict]:
        """List all configured MCP servers with their status."""
        config = self._load_config()
        result = []
        for name, cfg in config.get("servers", {}).items():
            status = "disconnected"
            tools = []
            error = None
            if name in self._sessions:
                status = "connected"
                tools = self._tools.get(name, [])
            if name in self._servers and self._servers[name].get("error"):
                status = "error"
                error = self._servers[name]["error"]
            result.append({
                "name": name,
                "type": cfg.get("type", "stdio"),
                "status": status,
                "tools": tools,
                "resources": self._resources.get(name, []) if status == "connected" else [],
                "prompts": self._prompts.get(name, []) if status == "connected" else [],
                "error": error,
                "command": cfg.get("command"),
                "args": cfg.get("args"),
                "url": cfg.get("url"),
            })
        return result

    def add_server(self, name: str, config: dict):
        """Add a new MCP server configuration."""
        full_config = self._load_config()
        full_config.setdefault("servers", {})[name] = config
        self._save_config(full_config)

    def remove_server(self, name: str):
        """Remove an MCP server configuration."""
        full_config = self._load_config()
        servers = full_config.get("servers", {})
        if name not in servers:
            raise KeyError(f"MCP server '{name}' not found")
        del servers[name]
        self._save_config(full_config)

    async def connect(self, name: str):
        """Connect to an MCP server (starts subprocess for stdio type)."""
        config = self._load_config()
        server_cfg = config.get("servers", {}).get(name)
        if not server_cfg:
            raise KeyError(f"MCP server '{name}' not configured")

        # Disconnect existing if any
        if name in self._sessions:
            await self.disconnect(name)

        server_type = server_cfg.get("type", "stdio")
        try:
            if server_type == "stdio":
                await self._connect_stdio(name, server_cfg)
            elif server_type == "remote":
                await self._connect_remote(name, server_cfg)
            else:
                raise ValueError(f"Unknown MCP server type: {server_type}")
            self._servers[name] = {"status": "connected", "error": None}
        except Exception as e:
            self._servers[name] = {"status": "error", "error": str(e)}
            raise

    async def _connect_stdio(self, name: str, cfg: dict):
        """Connect to a stdio MCP server."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = cfg.get("command", "")
        args = cfg.get("args", [])
        env_vars = cfg.get("env", {})

        # Merge with current env
        env = dict(os.environ)
        env.update(env_vars)

        server_params = StdioServerParameters(
            command=command, args=args, env=env,
        )

        transport_ctx = stdio_client(server_params)
        transport = await transport_ctx.__aenter__()
        read_stream, write_stream = transport

        session = ClientSession(read_stream, write_stream)
        await session.initialize()

        # Discover tools
        tools_resp = await session.list_tools()
        tool_list = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                "server": name,
            }
            for t in tools_resp.tools
        ]

        self._transports[name] = transport_ctx
        self._sessions[name] = session
        self._tools[name] = tool_list
        # Discover resources (best-effort, SDK session)
        try:
            res_resp = await session.list_resources()
            self._resources[name] = [
                {"uri": str(r.uri), "name": r.name or "", "description": getattr(r, "description", "") or "",
                 "mimeType": getattr(r, "mimeType", "") or "", "server": name}
                for r in res_resp.resources
            ]
        except Exception:
            self._resources[name] = []
        # Discover prompts (best-effort, SDK session)
        try:
            pr_resp = await session.list_prompts()
            self._prompts[name] = [
                {"name": p.name, "description": p.description or "",
                 "arguments": [{"name": a.name, "description": getattr(a, "description", "") or "",
                               "required": getattr(a, "required", False)} for a in (p.arguments or [])],
                 "server": name}
                for p in pr_resp.prompts
            ]
        except Exception:
            self._prompts[name] = []

    async def _connect_remote(self, name: str, cfg: dict):
        """Connect to a remote MCP server via Streamable HTTP.

        Uses a raw HTTP implementation because the MCP SDK's streamablehttp_client
        has a bug where session.initialize() hangs on certain servers (e.g. Tavily).
        Falls back to the SDK's SSE client if raw HTTP fails.
        """
        import httpx

        url = cfg.get("url", "")
        if not url:
            raise ValueError("Remote MCP server requires 'url'")

        extra_headers = cfg.get("headers", {})
        timeout = cfg.get("timeout", 60)

        # Try raw Streamable HTTP first (works around SDK bug)
        try:
            raw_session = RawStreamableHttpSession(url, headers=extra_headers, timeout=timeout)
            await raw_session.initialize()
            tools = await raw_session.list_tools()
            tool_list = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {}),
                    "server": name,
                }
                for t in tools
            ]
            self._transports[name] = None  # No context manager to clean up
            self._sessions[name] = raw_session
            self._tools[name] = tool_list
            # Discover resources (best-effort)
            try:
                resources = await raw_session.list_resources()
                self._resources[name] = [
                    {"uri": r.get("uri", ""), "name": r.get("name", ""), "description": r.get("description", ""),
                     "mimeType": r.get("mimeType", ""), "server": name}
                    for r in resources
                ]
            except Exception:
                self._resources[name] = []
            # Discover prompts (best-effort)
            try:
                prompts = await raw_session.list_prompts()
                self._prompts[name] = [
                    {"name": p.get("name", ""), "description": p.get("description", ""),
                     "arguments": p.get("arguments", []), "server": name}
                    for p in prompts
                ]
            except Exception:
                self._prompts[name] = []
            return
        except Exception as e:
            print(f"[MCP] Raw HTTP failed for '{name}': {e}, trying SDK SSE...")

        # Fall back to SDK SSE client
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        sse_headers = extra_headers if extra_headers else None
        transport_ctx = sse_client(url, headers=sse_headers)
        transport = await transport_ctx.__aenter__()
        read_stream, write_stream = transport
        session = ClientSession(read_stream, write_stream)
        await asyncio.wait_for(session.initialize(), timeout=timeout)

        tools_resp = await session.list_tools()
        tool_list = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                "server": name,
            }
            for t in tools_resp.tools
        ]

        self._transports[name] = transport_ctx
        self._sessions[name] = session
        self._tools[name] = tool_list
        # Discover resources (best-effort, SDK session)
        try:
            res_resp = await session.list_resources()
            self._resources[name] = [
                {"uri": str(r.uri), "name": r.name or "", "description": getattr(r, "description", "") or "",
                 "mimeType": getattr(r, "mimeType", "") or "", "server": name}
                for r in res_resp.resources
            ]
        except Exception:
            self._resources[name] = []
        # Discover prompts (best-effort, SDK session)
        try:
            pr_resp = await session.list_prompts()
            self._prompts[name] = [
                {"name": p.name, "description": p.description or "",
                 "arguments": [{"name": a.name, "description": getattr(a, "description", "") or "",
                               "required": getattr(a, "required", False)} for a in (p.arguments or [])],
                 "server": name}
                for p in pr_resp.prompts
            ]
        except Exception:
            self._prompts[name] = []

    async def disconnect(self, name: str):
        """Disconnect from an MCP server."""
        session = self._sessions.pop(name, None)
        transport_ctx = self._transports.pop(name, None)
        self._tools.pop(name, None)
        self._resources.pop(name, None)
        self._prompts.pop(name, None)

        # Close RawStreamableHttpSession if applicable
        if isinstance(session, RawStreamableHttpSession):
            try:
                await session.close()
            except Exception:
                pass

        if transport_ctx:
            try:
                await transport_ctx.__aexit__(None, None, None)
            except Exception:
                pass

        self._servers.pop(name, None)

    def get_all_tools(self) -> list[dict]:
        """Get all tools from all connected servers."""
        all_tools = []
        for tools in self._tools.values():
            all_tools.extend(tools)
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> dict:
        """Call a tool on a connected MCP server."""
        session = self._sessions.get(server_name)
        if not session:
            raise KeyError(f"MCP server '{server_name}' is not connected")

        # RawStreamableHttpSession returns plain dicts
        if isinstance(session, RawStreamableHttpSession):
            result = await session.call_tool(tool_name, arguments)
            content_parts = []
            for part in result.get("content", []):
                if isinstance(part, dict):
                    content_parts.append(part)
                else:
                    content_parts.append({"type": "text", "text": str(part)})
            return {
                "content": content_parts,
                "isError": result.get("isError", False),
            }

        # SDK ClientSession returns typed objects
        result = await session.call_tool(tool_name, arguments)
        content_parts = []
        for part in result.content:
            if hasattr(part, "text"):
                content_parts.append({"type": "text", "text": part.text})
            elif hasattr(part, "data"):
                content_parts.append({"type": "resource", "data": str(part.data)})
            else:
                content_parts.append({"type": "unknown", "value": str(part)})
        return {
            "content": content_parts,
            "isError": getattr(result, "isError", False),
        }

    def get_all_resources(self) -> list[dict]:
        """Get all resources from all connected servers."""
        all_res = []
        for res in self._resources.values():
            all_res.extend(res)
        return all_res

    async def read_resource(self, server_name: str, uri: str) -> dict:
        """Read a resource from a connected MCP server."""
        session = self._sessions.get(server_name)
        if not session:
            raise KeyError(f"MCP server '{server_name}' is not connected")
        if isinstance(session, RawStreamableHttpSession):
            return await session.read_resource(uri)
        result = await session.read_resource(uri)
        contents = []
        for part in result.contents:
            if hasattr(part, "text"):
                contents.append({"uri": str(part.uri), "text": part.text, "mimeType": getattr(part, "mimeType", "")})
            elif hasattr(part, "blob"):
                contents.append({"uri": str(part.uri), "blob": part.blob, "mimeType": getattr(part, "mimeType", "")})
            else:
                contents.append({"uri": str(part.uri), "text": str(part)})
        return {"contents": contents}

    def get_all_prompts(self) -> list[dict]:
        """Get all prompts from all connected servers."""
        all_pr = []
        for pr in self._prompts.values():
            all_pr.extend(pr)
        return all_pr

    async def get_prompt(self, server_name: str, prompt_name: str, arguments: dict | None = None) -> dict:
        """Get a prompt from a connected MCP server."""
        session = self._sessions.get(server_name)
        if not session:
            raise KeyError(f"MCP server '{server_name}' is not connected")
        if isinstance(session, RawStreamableHttpSession):
            return await session.get_prompt(prompt_name, arguments)
        result = await session.get_prompt(prompt_name, arguments)
        messages = []
        for msg in result.messages:
            parts = []
            content = msg.content
            if isinstance(content, list):
                for p in content:
                    if hasattr(p, "text"):
                        parts.append({"type": "text", "text": p.text})
            elif hasattr(content, "text"):
                parts.append({"type": "text", "text": content.text})
            messages.append({"role": msg.role, "content": parts})
        return {"messages": messages}

    async def refresh_server(self, name: str) -> dict:
        """Re-fetch tools/resources/prompts from a connected server."""
        session = self._sessions.get(name)
        if not session:
            raise KeyError(f"MCP server '{name}' is not connected")
        old_tools = len(self._tools.get(name, []))
        # Refresh tools
        if isinstance(session, RawStreamableHttpSession):
            tools = await session.list_tools()
            self._tools[name] = [
                {"name": t["name"], "description": t.get("description", ""),
                 "input_schema": t.get("inputSchema", {}), "server": name}
                for t in tools
            ]
            try:
                resources = await session.list_resources()
                self._resources[name] = [
                    {"uri": r.get("uri", ""), "name": r.get("name", ""), "description": r.get("description", ""),
                     "mimeType": r.get("mimeType", ""), "server": name}
                    for r in resources
                ]
            except Exception:
                pass
            try:
                prompts = await session.list_prompts()
                self._prompts[name] = [
                    {"name": p.get("name", ""), "description": p.get("description", ""),
                     "arguments": p.get("arguments", []), "server": name}
                    for p in prompts
                ]
            except Exception:
                pass
        else:
            tools_resp = await session.list_tools()
            self._tools[name] = [
                {"name": t.name, "description": t.description or "",
                 "input_schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                 "server": name}
                for t in tools_resp.tools
            ]
            try:
                res_resp = await session.list_resources()
                self._resources[name] = [
                    {"uri": str(r.uri), "name": r.name or "", "description": getattr(r, "description", "") or "",
                     "mimeType": getattr(r, "mimeType", "") or "", "server": name}
                    for r in res_resp.resources
                ]
            except Exception:
                pass
            try:
                pr_resp = await session.list_prompts()
                self._prompts[name] = [
                    {"name": p.name, "description": p.description or "",
                     "arguments": [{"name": a.name, "description": getattr(a, "description", "") or "",
                                   "required": getattr(a, "required", False)} for a in (p.arguments or [])],
                     "server": name}
                    for p in pr_resp.prompts
                ]
            except Exception:
                pass
        return {
            "tools": len(self._tools.get(name, [])),
            "resources": len(self._resources.get(name, [])),
            "prompts": len(self._prompts.get(name, [])),
            "tools_changed": old_tools != len(self._tools.get(name, [])),
        }


# Singleton MCP manager
mcp_manager = ContainerMcpManager()


@app.get("/mcp/servers")
async def list_mcp_servers():
    """List all configured MCP servers and their status."""
    return mcp_manager.list_servers()


@app.post("/mcp/servers")
async def add_mcp_server(req: AddMcpServerRequest):
    """Add a new MCP server configuration."""
    config = {"type": req.type, "timeout": req.timeout}
    if req.type == "stdio":
        if not req.command:
            raise HTTPException(status_code=400, detail="stdio server requires 'command'")
        config["command"] = req.command
        config["args"] = req.args or []
        config["env"] = req.env or {}
    elif req.type == "remote":
        if not req.url:
            raise HTTPException(status_code=400, detail="remote server requires 'url'")
        config["url"] = req.url
        if req.headers:
            config["headers"] = req.headers
    else:
        raise HTTPException(status_code=400, detail=f"Unknown type: {req.type}")
    mcp_manager.add_server(req.name, config)
    return {"ok": True, "message": f"MCP server '{req.name}' added"}


@app.delete("/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """Remove an MCP server configuration."""
    # Disconnect first if connected
    if name in mcp_manager._sessions:
        await mcp_manager.disconnect(name)
    try:
        mcp_manager.remove_server(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    return {"ok": True, "message": f"MCP server '{name}' removed"}


@app.post("/mcp/servers/{name}/connect")
async def connect_mcp_server(name: str):
    """Start and connect to an MCP server."""
    try:
        await mcp_manager.connect(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")
    return {"ok": True, "message": f"Connected to '{name}'"}


@app.post("/mcp/servers/{name}/disconnect")
async def disconnect_mcp_server(name: str):
    """Disconnect from an MCP server."""
    await mcp_manager.disconnect(name)
    return {"ok": True, "message": f"Disconnected from '{name}'"}


@app.get("/mcp/tools")
async def list_mcp_tools():
    """List all tools from all connected MCP servers."""
    return mcp_manager.get_all_tools()


@app.post("/mcp/tools/{server_name}/{tool_name}")
async def call_mcp_tool(server_name: str, tool_name: str, req: CallMcpToolRequest):
    """Call a tool on a connected MCP server."""
    try:
        result = await mcp_manager.call_tool(server_name, tool_name, req.arguments)
        return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Return MCP errors as tool results (isError=true) instead of HTTP 500.
        # This lets the LLM see the error and decide how to handle it.
        return {
            "content": [{"type": "text", "text": f"MCP tool error: {e}"}],
            "isError": True,
        }


@app.get("/mcp/resources")
async def list_mcp_resources():
    """List all resources from all connected MCP servers."""
    return mcp_manager.get_all_resources()


@app.post("/mcp/resources/read")
async def read_mcp_resource(req: ReadMcpResourceRequest):
    """Read a specific resource from a connected MCP server."""
    try:
        return await mcp_manager.read_resource(req.server, req.uri)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resource read failed: {e}")


@app.get("/mcp/prompts")
async def list_mcp_prompts():
    """List all prompts from all connected MCP servers."""
    return mcp_manager.get_all_prompts()


@app.post("/mcp/prompts/get")
async def get_mcp_prompt(req: GetMcpPromptRequest):
    """Get a specific prompt from a connected MCP server."""
    try:
        return await mcp_manager.get_prompt(req.server, req.name, req.arguments)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prompt get failed: {e}")


@app.post("/mcp/servers/{name}/refresh")
async def refresh_mcp_server(name: str):
    """Re-fetch tools/resources/prompts from a connected MCP server."""
    try:
        return await mcp_manager.refresh_server(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {e}")


# ============================================================
# Backup / Restore (GKE mode)
# ============================================================

MANIFEST_PATH = Path("/data/.manifest.json")
BACKUP_EXCLUDE = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".next", ".nuxt", "dist", "build", ".cache",
}


class BackupRequest(BaseModel):
    provider: str = "gcs"
    bucket: str = ""
    prefix: str = ""


def _scan_workspace(base: Path) -> dict[str, float]:
    """Scan /workspace and return {relative_path: mtime} excluding large dirs."""
    result = {}
    for p in base.rglob("*"):
        if p.is_file():
            parts = p.relative_to(base).parts
            if any(part in BACKUP_EXCLUDE for part in parts):
                continue
            try:
                result[str(p.relative_to(base))] = p.stat().st_mtime
            except OSError:
                pass
    return result


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"files": {}}


def _save_manifest(manifest: dict):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


@app.post("/backup")
def backup_workspace(req: BackupRequest):
    """Incremental backup of /workspace to cloud storage.

    Runs synchronously (FastAPI thread pool) to avoid blocking the event loop
    with GCS SDK calls, which would stall health checks.
    """
    if not req.bucket:
        return JSONResponse(status_code=200, content={"uploaded": 0, "message": "no bucket configured"})

    try:
        from google.cloud import storage as gcs
    except ImportError:
        raise HTTPException(status_code=501, detail="google-cloud-storage not installed")

    workspace = Path("/workspace")
    current_files = _scan_workspace(workspace)
    manifest = _load_manifest()
    old_files = manifest.get("files", {})

    client = gcs.Client()
    bucket = client.bucket(req.bucket)

    uploaded = 0
    deleted = 0
    total_size = 0

    # Upload new or modified files
    for rel_path, mtime in current_files.items():
        if rel_path in old_files and old_files[rel_path] >= mtime:
            continue
        file_path = workspace / rel_path
        blob_key = f"{req.prefix}{rel_path}" if req.prefix else rel_path
        blob = bucket.blob(blob_key)
        data = file_path.read_bytes()
        blob.upload_from_string(data)
        total_size += len(data)
        uploaded += 1

    # Delete removed files from cloud
    for rel_path in old_files:
        if rel_path not in current_files:
            blob_key = f"{req.prefix}{rel_path}" if req.prefix else rel_path
            blob = bucket.blob(blob_key)
            try:
                blob.delete()
            except Exception:
                pass
            deleted += 1

    manifest["files"] = {k: v for k, v in current_files.items()}
    _save_manifest(manifest)

    # Upload manifest to cloud as well
    manifest_key = f"{req.prefix}.manifest.json" if req.prefix else ".manifest.json"
    bucket.blob(manifest_key).upload_from_string(json.dumps(manifest))

    return {
        "uploaded": uploaded,
        "deleted": deleted,
        "total_size": f"{total_size / (1024 * 1024):.1f}MB",
    }


@app.post("/restore")
def restore_workspace(req: BackupRequest):
    """Restore /workspace from cloud storage.

    Runs synchronously (FastAPI thread pool) to avoid blocking the event loop
    with GCS SDK calls, which would stall health checks.
    """
    if not req.bucket:
        return JSONResponse(status_code=200, content={"restored": 0, "message": "no bucket configured"})

    try:
        from google.cloud import storage as gcs
    except ImportError:
        raise HTTPException(status_code=501, detail="google-cloud-storage not installed")

    client = gcs.Client()
    bucket = client.bucket(req.bucket)
    workspace = Path("/workspace")

    # Download manifest
    manifest_key = f"{req.prefix}.manifest.json" if req.prefix else ".manifest.json"
    manifest_blob = bucket.blob(manifest_key)
    if not manifest_blob.exists():
        return {"restored": 0, "message": "no backup found"}

    manifest = json.loads(manifest_blob.download_as_bytes())
    files_map = manifest.get("files", {})

    restored = 0
    total_size = 0

    for rel_path, mtime in files_map.items():
        blob_key = f"{req.prefix}{rel_path}" if req.prefix else rel_path
        blob = bucket.blob(blob_key)
        if not blob.exists():
            continue
        data = blob.download_as_bytes()
        file_path = workspace / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data)
        os.utime(file_path, (mtime, mtime))
        total_size += len(data)
        restored += 1

    _save_manifest(manifest)

    return {
        "restored": restored,
        "total_size": f"{total_size / (1024 * 1024):.1f}MB",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
