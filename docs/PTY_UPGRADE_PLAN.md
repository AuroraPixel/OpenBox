# OpenBox 终端升级计划: 命令-响应模式 → PTY 交互模式

> 状态: **已完成**
> 优先级: 高
> 前置条件: 第一阶段基础平台已完成

## 目标

将终端从"发送完整命令行 → 等待返回完整结果"改为真正的 PTY（伪终端）模式，支持：
- 交互式程序: python3 REPL、vim、nano、htop、top、less、ssh 等
- Shell 特性: Tab 补全、箭头键历史、Ctrl+C/D/Z 等信号
- 持久会话: 环境变量、cd 目录、shell 历史在会话内保持
- 终端大小同步: 浏览器窗口缩放时自动适配

## 架构变更

```
当前（命令-响应）:
  xterm.js --JSON{"type":"input","data":"ls"}--> Backend --HTTP POST /execute--> Container (每次新建subprocess)
  xterm.js <--JSON{"type":"output","data":"..."}<-- Backend <--HTTP Response<-- Container

升级后（PTY 流式）:
  xterm.js --二进制帧(原始按键)--> Backend WS relay --二进制帧--> Container WS --write()--> PTY master fd
  xterm.js <--二进制帧(终端输出)<-- Backend WS relay <--二进制帧<-- Container WS <--read()<-- PTY master fd
```

关键变化：
1. 容器内创建真正的 PTY + bash 持久进程（而非每次 subprocess）
2. 按键级实时流式传输（而非行级命令-响应）
3. 二进制帧协议（而非 JSON 文本）
4. 后端从 HTTP 转发改为 WebSocket 双向中继

## 二进制帧协议

所有 WebSocket binary frame 使用 **1 字节前缀** 区分消息类型：

| 前缀字节 | 方向 | 含义 | payload |
|----------|------|------|---------|
| `0x00` | 双向 | 终端数据 | 原始 PTY 字节流 |
| `0x01` | 客户端→服务端 | 窗口大小变更 | cols(2B big-endian) + rows(2B big-endian) |

JSON text frame 保留用于控制消息（heartbeat、error 通知）。

## 修改文件清单

### 1. `container/action_server.py` — 新增 WebSocket `/terminal` 端点

**保留**: 所有现有 HTTP 端点（`/alive`、`/execute`、`/upload`、`/download`、`/list_files`、`/system_info`）不变。

**新增** `/terminal` WebSocket 端点：

```
新增 import: os, pty, fcntl, struct, termios, signal, subprocess

@app.websocket("/terminal")
async def terminal_ws(ws: WebSocket, api_key: str = Query("")):
```

实现要点：
- **认证**: 通过 query parameter `?api_key=xxx`（WebSocket 不经过 HTTP 中间件）
- **PTY 创建**: `pty.openpty()` 获取 master_fd / slave_fd
- **子进程**: `os.fork()` → 子进程中 `os.setsid()` + `TIOCSCTTY` 设置控制终端 → 切换到 sandbox 用户(uid=1000, gid=1000) → `os.execve("/bin/bash", ["bash", "--login"], env)`
- **环境变量**: `TERM=xterm-256color`, `HOME=/home/sandbox`, `USER=sandbox`, `LANG=C.UTF-8`
- **工作目录**: `/workspace`
- **master_fd 设为 non-blocking**: `fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)`
- **双向流**:
  - `read_pty_to_ws`: 用 `loop.run_in_executor(None, os.read, master_fd, 4096)` 阻塞读取 → 发送 `b"\x00" + data`
  - `read_ws_to_pty`: 接收二进制帧 → 前缀 `0x00` 写入 master_fd / 前缀 `0x01` 解析 cols/rows 后 `TIOCSWINSZ` + `SIGWINCH`
- **清理**: `SIGTERM` → sleep 0.1s → `SIGKILL` → `os.waitpid` → `os.close(master_fd)` → `ws.close()`
- 用 `asyncio.wait(FIRST_COMPLETED)` 等待任一任务结束后触发全面清理

### 2. `backend/app/api/terminal.py` — 改为 WS↔WS 双向中继

**完全重写**。从 HTTP POST 转发改为 WebSocket 到 WebSocket 的透明中继。

```python
import websockets  # 已在 pyproject.toml 依赖中

@router.websocket("/ws/terminal/{container_id}")
async def terminal_websocket(websocket: WebSocket, container_id: str):
```

实现要点：
- 获取容器信息: `info = await docker_manager.get_container(container_id)` → `info.port` + `info.api_key`
- 连接容器 WS: `websockets.connect(f"ws://localhost:{port}/terminal?api_key={key}")`
- 两个并发中继任务:
  - `frontend_to_container`: `websocket.receive()` → 区分 bytes/text → `container_ws.send()`
  - `container_to_frontend`: `async for msg in container_ws` → 区分 bytes/str → `websocket.send_bytes/send_text()`
- binary 和 text frame 直接透传，后端不解析帧内容
- cleanup: cancel tasks → close 两端连接

### 3. `frontend/src/hooks/useWebSocket.ts` — 支持二进制帧

**增量修改**，向后兼容：

- `ws.binaryType = "arraybuffer"` — 二进制帧以 ArrayBuffer 接收
- 新增选项: `onBinaryMessage?: (data: ArrayBuffer) => void`
- `onmessage` 中: `event.data instanceof ArrayBuffer` → 调用 `onBinaryMessage`，否则 JSON.parse → 调用 `onMessage`
- 新增方法: `sendBinary(data: Uint8Array | ArrayBuffer)` — 发送二进制帧
- 返回值新增: `sendBinary`

### 4. `frontend/src/types/index.ts` — 新增协议常量

```typescript
// 二进制帧协议前缀
export const TERMINAL_MSG_DATA = 0x00
export const TERMINAL_MSG_RESIZE = 0x01
```

保留现有 `WSMessage` 接口不变（用于 JSON 控制消息）。

### 5. `frontend/src/components/terminal/Terminal.tsx` — 重写为 PTY 直通

**删除**:
- `inputBufferRef` — 手动行编辑缓冲区
- `isFirstMessageRef` — 连接消息特殊处理
- `handleMessage` 中的 output/error 解析和 `$` 提示符渲染
- `onData` 中的 Enter/Backspace/Ctrl+C 手动处理逻辑

**新增**:
- `handleBinaryMessage(data: ArrayBuffer)`: 解析前缀 → `0x00` 时 `xterm.write(new Uint8Array(payload))` 直接输出原始字节
- `handleMessage` 仅处理 JSON error 消息
- `xterm.onData(data)`: **每个按键立即发送** → 构造 `[0x00, ...encode(data)]` 二进制帧 → `sendBinary()`
- `xterm.onBinary(data)`: 处理 xterm 二进制序列（鼠标事件等）
- `sendResize(cols, rows)`: 构造 `[0x01, colsHi, colsLo, rowsHi, rowsLo]` 二进制帧
- `ResizeObserver` + `xterm.onResize`: 检测大小变化 → `sendResize()`
- `useEffect([connected])`: 连接建立后发送初始 resize

**核心理念**: 前端变为纯粹的终端仿真器，不做任何输入/输出处理，所有行编辑、提示符、补全由远端 bash PTY 负责。

## 不修改的文件

- `container/Dockerfile` — bash 和 Python pty 模块已内置
- `container/requirements.txt` — FastAPI 原生支持 WebSocket，无需新依赖
- `backend/app/core/docker_manager.py` — 不涉及终端逻辑
- `backend/app/api/containers.py` / `files.py` — 不涉及
- 其他前端组件 — 不涉及

## 实施步骤

```
1. 修改 container/action_server.py     — 添加 /terminal WebSocket 端点
2. 重新构建沙箱镜像                      — docker build -t openbox-sandbox:latest ./container
3. 修改 backend/app/api/terminal.py     — 改为 WS↔WS 中继
4. 修改 frontend/src/types/index.ts     — 添加协议常量
5. 修改 frontend/src/hooks/useWebSocket.ts — 支持二进制帧
6. 修改 frontend/src/components/terminal/Terminal.tsx — 重写为 PTY 直通
7. 端到端测试
```

## 验证清单

构建与启动：
- [ ] `docker build -t openbox-sandbox:latest ./container` 成功
- [ ] 后端启动无报错
- [ ] 前端 `tsc -b` 和 `vite build` 无错误

功能测试：
- [ ] 打开终端看到 bash 提示符（非前端伪造的 `$`）
- [ ] 基础命令: `ls -la`, `echo hello`, `cat /etc/passwd` 正常输出
- [ ] Tab 补全: 输入 `ls /e` 按 Tab 自动补全为 `/etc/`
- [ ] 箭头键: ↑↓ 翻历史命令, ←→ 移动光标
- [ ] 持久会话: `export FOO=bar` → `echo $FOO` 输出 `bar`；`cd /tmp` → `pwd` 输出 `/tmp`
- [ ] Python REPL: `python3` → `1+1` → `Ctrl+D` 退出回到 bash
- [ ] vim: `vim test.txt` → 输入内容 → `:wq` 保存退出
- [ ] htop: 正常显示 TUI → `q` 退出
- [ ] Ctrl+C: 中断运行中的命令（如 `sleep 100`）
- [ ] 窗口缩放: 拖动浏览器窗口，终端内容自动适配、TUI 程序重绘正确
- [ ] 创建多个容器，各终端独立运行
- [ ] 关闭终端标签后重新打开，获得新 PTY 会话
- [ ] 删除容器后终端显示断连提示
