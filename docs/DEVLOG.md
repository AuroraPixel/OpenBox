# OpenBox 开发日志

## 项目概述

OpenBox 是一个 Web 沙箱管理平台，参考 [OpenHands](https://github.com/All-Hands-AI/OpenHands) 的沙箱架构设计，提供通过 WebUI 创建、管理 Docker 沙箱容器并与容器内终端实时通讯的能力。

### 架构

```
WebUI (React+Vite+TailwindCSS) ←→ REST/WebSocket ←→ Backend (FastAPI) ←→ HTTP ←→ Container Action Server (FastAPI)
```

- **前端**: React 19 + Vite 6 + TailwindCSS 4 + xterm.js + lucide-react
- **后端**: Python 3.12 + FastAPI + docker-py + httpx，使用 uv 管理依赖
- **容器服务**: 每个沙箱容器内运行一个轻量 FastAPI Action Server，提供命令执行、文件管理等 API
- **通讯**: 前端通过 WebSocket 连接后端，后端作为代理转发请求到容器

---

## 第一阶段：基础平台搭建（已完成）

### 设计分析

在实现前，对 OpenHands 项目进行了深入分析：

1. **沙箱架构**: OpenHands 使用 Docker 容器作为沙箱，每个会话独立一个容器（`container_name = openhands-runtime-{sid}`）
2. **LLM Agent 位置**: LLM Agent 在外部（Python 进程），Docker 容器内只有 Action Execution Server（无 LLM）
3. **通讯模式**: 外部 Agent 通过 HTTP REST 调用容器内的 Action Server
4. **容器初始化**: 基于 Dockerfile.j2 模板构建，预装 Python 环境（micromamba + poetry）、Node.js、常用工具

### 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 后端代理模式 | 前端不直接访问容器端口 | 安全性，API Key 对前端透明 |
| 终端通讯 | WebSocket 命令-响应模式 | 第一阶段简单可靠 |
| 端口分配 | 10000-19999 动态分配 | socket bind 检测可用端口 |
| 容器安全 | 内存 512MB / CPU 0.5 核 / tini init | 资源隔离 |
| API Key | 每容器独立 key，环境变量注入 | 容器间隔离认证 |

### 实现过程

使用 4 个并行 Agent 同时开发：

- **Agent A (容器服务)**: 创建 `container/action_server.py`、`Dockerfile`、`requirements.txt`
- **Agent B (后端 API)**: 创建 12 个后端文件（FastAPI 应用完整结构）
- **Agent C (前端 WebUI)**: 创建所有 React 组件源文件（因权限限制未完成 npm install）
- **Agent D (基础设施)**: 创建 `docker-compose.yml`、`Makefile`、`.gitignore`、Dockerfile、nginx.conf

### 后续修复

Agent 完成后进行了以下修复：

1. **前端 npm 依赖安装** — Agent C 因子进程权限限制无法执行 npm 命令，手动完成
2. **xterm 包迁移** — 从已废弃的 `xterm` 迁移到 `@xterm/xterm@^5.5.0`，更新 Terminal.tsx 中的 import
3. **添加 `@types/node`** — 修复 vite.config.ts 中 `path` 和 `__dirname` 的类型错误
4. **pyproject.toml 修复** — 添加 `[tool.hatch.build.targets.wheel] packages = ["app"]`，解决 hatchling 找不到包的问题
5. **docker_manager.py 异步修复（关键）** — 所有 Docker SDK 阻塞调用（`containers.run`、`containers.get`、`container.remove`、`container.stop`、`container.start`、`containers.list`）都用 `loop.run_in_executor()` 包装，避免阻塞 asyncio 事件循环
6. **`_wait_until_ready` 日志改进** — 添加尝试计数和分类错误处理

### 端到端验证结果

| 端点 | 状态 |
|------|------|
| `GET /health` | OK |
| `POST /api/containers` (创建) | OK |
| `GET /api/containers` (列表) | OK |
| `DELETE /api/containers/:id` (删除) | OK |
| `POST /api/containers/:id/files/list` | OK |
| `GET /api/containers/:id/files/system_info` | OK |
| `WS /ws/terminal/:id` (命令执行) | OK |

---

## 项目文件结构

```
OpenBox/
├── docker-compose.yml          # 开发编排（backend + frontend）
├── Makefile                    # 常用命令（dev, build, up, down, clean）
├── .gitignore
├── docs/
│   ├── DEVLOG.md               # 本文件 - 开发日志
│   └── PTY_UPGRADE_PLAN.md     # PTY 升级计划
├── container/
│   ├── action_server.py        # 容器内 FastAPI 服务（6个端点 + API Key 中间件）
│   ├── Dockerfile              # python:3.12-slim + 工具 + sandbox 用户
│   └── requirements.txt        # fastapi, uvicorn, psutil, python-multipart
├── backend/
│   ├── pyproject.toml          # uv 项目配置
│   ├── Dockerfile
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI 入口，CORS，lifespan，/health
│       ├── models/
│       │   ├── __init__.py
│       │   └── schemas.py      # Pydantic 模型
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py       # Settings 配置（端口范围、镜像名等）
│       │   └── docker_manager.py  # Docker 容器 CRUD + HTTP 转发（核心）
│       └── api/
│           ├── __init__.py
│           ├── containers.py   # REST: POST/GET/DELETE /api/containers
│           ├── terminal.py     # WebSocket: /ws/terminal/{id}
│           └── files.py        # 文件列表 + 系统信息代理
└── frontend/
    ├── package.json
    ├── vite.config.ts          # Vite + TailwindCSS + 路径别名 + 代理
    ├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
    ├── index.html
    ├── Dockerfile              # 多阶段构建（node builder → nginx）
    ├── nginx.conf              # SPA 路由 + API/WS 反向代理
    └── src/
        ├── main.tsx
        ├── App.tsx             # 主布局（侧边栏 + 终端面板）
        ├── index.css           # TailwindCSS
        ├── vite-env.d.ts
        ├── lib/utils.ts        # cn() 工具函数
        ├── types/index.ts      # TypeScript 类型定义
        ├── services/api.ts     # API 封装（fetch + WS URL 生成）
        ├── hooks/
        │   ├── useContainers.ts  # 容器 CRUD 状态管理（5s 轮询）
        │   └── useWebSocket.ts   # WebSocket hook（自动重连）
        └── components/
            ├── layout/
            │   ├── Header.tsx    # 顶部栏（logo + 容器计数）
            │   └── Sidebar.tsx   # 侧边栏（新建按钮 + 容器列表）
            ├── containers/
            │   ├── ContainerCard.tsx          # 容器卡片（状态指示器 + 操作按钮）
            │   ├── ContainerList.tsx          # 容器列表
            │   └── CreateContainerDialog.tsx  # 创建对话框
            └── terminal/
                ├── Terminal.tsx      # xterm.js 终端（核心组件）
                └── TerminalTabs.tsx  # 多终端标签管理
```

---

## 启动方式

```bash
# 1. 构建沙箱镜像
docker build -t openbox-sandbox:latest ./container

# 2. 启动后端（终端 1）
cd backend
~/.local/bin/uv run uvicorn app.main:app --reload --port 8080

# 3. 启动前端（终端 2）
cd frontend
npm run dev
```

前端访问 `http://localhost:5173`，Vite 自动代理 `/api` 和 `/ws` 请求到后端 8080 端口。

---

## 第二阶段：PTY 终端升级（已完成）

### 概述

将终端从"命令-响应"模式升级为真正的 PTY（伪终端）交互模式，支持交互式程序（python3 REPL、vim、htop）、Shell 特性（Tab 补全、箭头键历史、Ctrl+C/D/Z）、持久会话和终端大小同步。

### 架构变更

```
升级前（命令-响应）:
  xterm.js --JSON--> Backend --HTTP POST /execute--> Container (每次新建 subprocess)

升级后（PTY 流式）:
  xterm.js --二进制帧(原始按键)--> Backend WS relay --二进制帧--> Container WS --write()--> PTY master fd
  xterm.js <--二进制帧(终端输出)<-- Backend WS relay <--二进制帧<-- Container WS <--read()<-- PTY master fd
```

### 二进制帧协议

所有 WebSocket binary frame 使用 1 字节前缀区分消息类型：

| 前缀字节 | 方向 | 含义 | payload |
|----------|------|------|---------|
| `0x00` | 双向 | 终端数据 | 原始 PTY 字节流 |
| `0x01` | 客户端→服务端 | 窗口大小变更 | cols(2B big-endian) + rows(2B big-endian) |

### 修改文件

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `container/action_server.py` | 新增端点 | 添加 `/terminal` WebSocket 端点：`pty.openpty()` + `os.fork()` + `os.execve()` 创建 PTY bash 会话 |
| `container/requirements.txt` | 修改 | `uvicorn` → `uvicorn[standard]` 以支持 WebSocket |
| `backend/app/api/terminal.py` | 重写 | 从 HTTP POST 转发改为 WS↔WS 透明中继，使用 `websockets` 库连接容器 |
| `frontend/src/hooks/useWebSocket.ts` | 增量修改 | 添加 `binaryType = "arraybuffer"`、`onBinaryMessage` 回调、`sendBinary` 方法 |
| `frontend/src/types/index.ts` | 新增常量 | `TERMINAL_MSG_DATA = 0x00`、`TERMINAL_MSG_RESIZE = 0x01` |
| `frontend/src/components/terminal/Terminal.tsx` | 重写 | 删除手动行编辑逻辑，改为每个按键即时发送二进制帧，xterm 直接渲染 PTY 输出 |

### 实现细节

**容器端 (`action_server.py`)**:
- `pty.openpty()` 创建 master/slave fd 对
- `os.fork()` 子进程中 `os.setsid()` + `TIOCSCTTY` 设置控制终端
- 切换到 sandbox 用户 (uid/gid) → `os.execve("/bin/bash", ["bash", "--login"], env)`
- master_fd 设为 non-blocking，通过 `loop.run_in_executor()` 阻塞读取
- `_blocking_read()` 使用 `select` 超时 0.5s，返回 `None` 表示 fd 错误，`b""` 表示超时
- 清理流程: SIGTERM → 0.1s → SIGKILL → waitpid → close fd → close ws

**后端中继 (`terminal.py`)**:
- `websockets.connect()` 连接容器 `/terminal?api_key=xxx`
- `frontend_to_container` + `container_to_frontend` 两个并发 task 透明转发
- binary 和 text frame 直接透传，后端不解析帧内容

**前端 (`Terminal.tsx`)**:
- `xterm.onData()` 每个按键立即构造 `[0x00, ...encoded]` 发送
- `xterm.onBinary()` 处理鼠标等二进制事件
- `xterm.onResize()` + `ResizeObserver` 发送 `[0x01, colsHi, colsLo, rowsHi, rowsLo]`
- 连接建立后发送初始 resize 同步终端尺寸

### Code Review 发现及修复

经过两轮 code review，发现并修复了以下问题：

| 优先级 | 问题 | 修复 |
|--------|------|------|
| P1 | `_blocking_read` 内 `while True` 循环永不返回，阻塞 executor 线程 | 移除循环，改为单次 `select` 调用 |
| P1 | WebSocket 认证失败时 `ws.close()` 在 `ws.accept()` 之前调用 | 先 `accept()` 再 `close()` |
| P2 | `asyncio.get_event_loop()` 已废弃 | 改为 `asyncio.get_running_loop()` |
| P2 | `asyncio.ensure_future()` 已废弃 | 改为 `asyncio.create_task()` |
| P2 | `_blocking_read` 返回 `b""` 超时导致 `if not data: break` 误退出 | 区分 `None`(fd 错误) 和 `b""`(超时) |
| P2 | 前端 `connectedRef` 未使用的死代码 | 删除 |
| P3 | `bytes.slice()` 不如 `bytes.subarray()` 高效 | 改为 `subarray()` |

### 运行时问题及修复

| 问题 | 原因 | 修复 |
|------|------|------|
| 容器 WS 握手返回 HTTP 403 | HTTP 中间件拦截了 `/terminal` 路径的 WebSocket 升级请求 | 将 `"/terminal"` 加入中间件白名单 |
| 容器返回 "No supported WebSocket library detected" | uvicorn 基础安装不含 WebSocket 支持 | `requirements.txt` 改为 `uvicorn[standard]>=0.32.0` |

### 测试结果

11/11 端到端测试通过：

- PTY 连接建立、echo 输出、pwd 工作目录
- 环境变量持久性 (`export FOO=bar` → `echo $FOO`)
- Ctrl+C 中断信号、终端 resize
- whoami 用户身份、后端 WS 中继 (3 项)、认证拒绝

---

## 当前已知限制

1. ~~**终端为命令-响应模式**~~ — ✅ 已升级为 PTY 交互模式
2. **无用户认证** — 后端 API 无登录/权限控制
3. **容器状态非持久化** — 后端重启后丢失容器映射（容器本身仍在 Docker 中）
4. **单机部署** — 不支持多节点
