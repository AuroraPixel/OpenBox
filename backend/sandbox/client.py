"""HTTP client for communicating with the Action Server inside a sandbox container."""
import asyncio
import json
import shlex
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from core.log import create_logger

log = create_logger("sandbox.client")


@dataclass
class ExecuteResult:
    """Result of a command execution."""
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class OutputChunk:
    """A streaming output chunk from execute_stream."""
    type: str  # "stdout", "stderr", "system"
    content: str


@dataclass
class IdleNotification:
    """Notification that the command has produced no output for a while."""
    idle_seconds: int
    total_seconds: int
    pid: int


class SandboxClient:
    """HTTP client for the Action Server running inside a sandbox container.

    All file and command operations go through this client to the sandbox.
    """

    def __init__(self, host: str, port: int, api_key: str):
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key
        self._headers = {"X-API-Key": api_key}

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        """Create an httpx async client."""
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=timeout,
        )

    async def execute(
        self,
        command: str,
        timeout: int = 120,
        workdir: str = "/workspace",
    ) -> ExecuteResult:
        """Execute a command in the sandbox."""
        async with self._client(timeout=timeout + 10) as client:
            resp = await client.post("/execute", json={
                "command": command,
                "timeout": timeout,
                "workdir": workdir,
            })
            resp.raise_for_status()
            data = resp.json()
            return ExecuteResult(
                exit_code=data["exit_code"],
                stdout=data["stdout"],
                stderr=data["stderr"],
            )

    async def execute_stream(
        self,
        command: str,
        timeout: int = 120,
        idle_timeout: int = 60,
        workdir: str = "/workspace",
    ) -> AsyncIterator[OutputChunk | IdleNotification | int]:
        """Execute a command with streaming output.

        Yields OutputChunk for each line of output,
        IdleNotification when no output for idle_timeout seconds,
        and finally the exit code (int) at the end.
        """
        pid = 0
        async with self._client(timeout=timeout + 10) as client:
            async with client.stream("POST", "/execute_stream", json={
                "command": command,
                "timeout": timeout,
                "idle_timeout": idle_timeout,
                "workdir": workdir,
            }) as resp:
                resp.raise_for_status()
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if "type" in data and "content" in data:
                                yield OutputChunk(
                                    type=data["type"],
                                    content=data["content"],
                                )
                            elif "exit_code" in data:
                                yield data["exit_code"]
                            elif "pid" in data and "idle_seconds" not in data:
                                pid = data["pid"]
                            elif "idle_seconds" in data:
                                yield IdleNotification(
                                    idle_seconds=data["idle_seconds"],
                                    total_seconds=data["total_seconds"],
                                    pid=pid,
                                )

    async def read_file(
        self,
        path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read a file from the sandbox with line numbers."""
        async with self._client() as client:
            resp = await client.post("/read_file", json={
                "path": path,
                "offset": offset,
                "limit": limit,
            })
            resp.raise_for_status()
            data = resp.json()
            return data["content"]

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file in the sandbox."""
        async with self._client() as client:
            resp = await client.post("/write_file", json={
                "path": path,
                "content": content,
            })
            resp.raise_for_status()

    async def glob(self, pattern: str, path: str = "/workspace") -> list[str]:
        """Find files matching a glob pattern in the sandbox."""
        async with self._client() as client:
            resp = await client.post("/glob", json={
                "pattern": pattern,
                "path": path,
            })
            resp.raise_for_status()
            data = resp.json()
            return data["files"]

    async def grep(
        self,
        pattern: str,
        path: str = "/workspace",
        file_type: str | None = None,
        max_results: int = 100,
    ) -> str:
        """Search file contents in the sandbox."""
        async with self._client() as client:
            resp = await client.post("/grep", json={
                "pattern": pattern,
                "path": path,
                "type": file_type,
                "max_results": max_results,
            })
            resp.raise_for_status()
            data = resp.json()
            return data["output"]

    async def list_files(self, path: str = "/workspace") -> list[dict]:
        """List directory contents in the sandbox."""
        async with self._client() as client:
            resp = await client.post("/list_files", json={"path": path})
            resp.raise_for_status()
            data = resp.json()
            return data["entries"]

    async def read_file_raw(self, path: str) -> str:
        """Read raw file content from the sandbox (no line numbers)."""
        result = await self.execute(f"cat {shlex.quote(path)}", timeout=10)
        if result.exit_code != 0:
            raise FileNotFoundError(f"File not found: {path}")
        return result.stdout

    async def kill_command(self, pid: int) -> None:
        """Kill a running command by PID via the action server."""
        try:
            async with self._client(timeout=5) as client:
                resp = await client.post("/kill", json={"pid": pid})
                resp.raise_for_status()
        except Exception as e:
            log.warning(f"Failed to kill process {pid}: {e}")

    async def alive(self) -> bool:
        """Check if the sandbox is alive."""
        try:
            async with self._client(timeout=5) as client:
                resp = await client.get("/alive")
                return resp.status_code == 200
        except Exception:
            return False

    # ---- Generic HTTP helpers ----

    async def _get(self, path: str, timeout: float = 15.0):
        """Generic GET request to action server."""
        async with self._client(timeout=timeout) as client:
            resp = await client.get(path)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, timeout: float = 30.0, **kwargs):
        """Generic POST request to action server."""
        async with self._client(timeout=timeout) as client:
            resp = await client.post(path, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def _delete(self, path: str, timeout: float = 15.0):
        """Generic DELETE request to action server."""
        async with self._client(timeout=timeout) as client:
            resp = await client.request("DELETE", path)
            resp.raise_for_status()
            return resp.json()

    # ---- Dev-browser management ----

    async def start_dev_browser(self) -> dict:
        """Start the dev-browser relay server inside the container."""
        return await self._post("/dev-browser/start", timeout=15.0)

    async def stop_dev_browser(self) -> dict:
        """Stop the dev-browser relay server."""
        return await self._post("/dev-browser/stop")

    async def get_dev_browser_status(self) -> dict:
        """Get dev-browser relay status and extension connection state."""
        return await self._get("/dev-browser/status")

    # ---- Skill management ----

    async def list_skills(self) -> list[dict]:
        """List all installed skills in the container."""
        return await self._get("/skills")

    async def get_skill(self, name: str) -> dict:
        """Get a specific skill by name."""
        return await self._get(f"/skills/{name}")

    async def install_skill(
        self,
        url: str | None = None,
        name: str | None = None,
        content: str | None = None,
    ) -> dict:
        """Install a skill in the container."""
        return await self._post(
            "/skills/install",
            timeout=90.0,
            json={"url": url, "name": name, "content": content},
        )

    async def upload_skill_archive(self, file_bytes: bytes, filename: str, name: str = "") -> dict:
        """Upload a skill archive (zip/tar/tar.gz/rar) to the container."""
        import httpx
        files = {"file": (filename, file_bytes)}
        data = {"name": name or ""}
        async with httpx.AsyncClient(timeout=90.0) as client:
            url = f"{self.base_url}/skills/upload"
            resp = await client.post(url, files=files, data=data, headers=self._headers)
            if resp.status_code != 200:
                detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                raise Exception(detail)
            return resp.json()

    async def uninstall_skill(self, name: str) -> dict:
        """Uninstall a skill from the container."""
        return await self._delete(f"/skills/{name}")

    # ---- MCP server management ----

    async def list_mcp_servers(self) -> list[dict]:
        """List all MCP servers configured in the container."""
        return await self._get("/mcp/servers")

    async def add_mcp_server(self, name: str, config: dict) -> dict:
        """Add a new MCP server configuration."""
        return await self._post("/mcp/servers", json={"name": name, **config})

    async def remove_mcp_server(self, name: str) -> dict:
        """Remove an MCP server configuration."""
        return await self._delete(f"/mcp/servers/{name}")

    async def connect_mcp(self, name: str) -> dict:
        """Connect to an MCP server."""
        return await self._post(f"/mcp/servers/{name}/connect")

    async def disconnect_mcp(self, name: str) -> dict:
        """Disconnect from an MCP server."""
        return await self._post(f"/mcp/servers/{name}/disconnect")

    async def list_mcp_tools(self) -> list[dict]:
        """List all tools from connected MCP servers."""
        return await self._get("/mcp/tools")

    async def call_mcp_tool(self, server: str, tool: str, arguments: dict) -> dict:
        """Call a tool on a connected MCP server."""
        return await self._post(
            f"/mcp/tools/{server}/{tool}",
            timeout=60.0,
            json={"arguments": arguments},
        )

    async def list_mcp_resources(self) -> list[dict]:
        """List all resources from connected MCP servers."""
        return await self._get("/mcp/resources")

    async def read_mcp_resource(self, server: str, uri: str) -> dict:
        """Read a specific MCP resource."""
        return await self._post("/mcp/resources/read", timeout=30.0, json={"server": server, "uri": uri})

    async def list_mcp_prompts(self) -> list[dict]:
        """List all prompts from connected MCP servers."""
        return await self._get("/mcp/prompts")

    async def get_mcp_prompt(self, server: str, name: str, arguments: dict | None = None) -> dict:
        """Get a specific MCP prompt."""
        return await self._post("/mcp/prompts/get", timeout=30.0, json={"server": server, "name": name, "arguments": arguments})

    async def refresh_mcp_server(self, name: str) -> dict:
        """Refresh tools/resources/prompts for a connected MCP server."""
        return await self._post(f"/mcp/servers/{name}/refresh", timeout=30.0)
