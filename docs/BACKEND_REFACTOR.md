# OpenBox Backend 重构总结

## 概述

将原有三个独立的后端包 (`backend/app/`、`backend/openagent/`、`backend/openbox/`) 合并为统一的扁平结构 `backend/`，实现沙箱管理 + AI Agent 平台的完整后端。

## 架构变更

### 之前（三包分离）
```
backend/
├── app/           # 旧版沙箱管理（11个文件），使用 app.* 导入
├── openagent/     # AI Agent 框架（60+文件），使用 openagent.* 导入
└── openbox/       # 合并包（尝试合并但嵌套过深）
```

### 之后（扁平统一）
```
backend/
├── agent/         # AI Agent 核心（loop、llm、hooks、retry、compaction）
├── api/           # FastAPI HTTP 路由（sessions、events、permissions 等）
├── bus/           # 进程内 async pub/sub 事件总线
├── command/       # 自定义命令系统
├── core/          # 基础设施（config、log、identifier、token、wildcard）
├── mcp/           # MCP 协议客户端
├── models/        # Pydantic 数据模型（message、container）
├── permission/    # 权限系统（rule 评估、ask/reply 用户授权）
├── project/       # 项目实例管理
├── question/      # 用户问答系统
├── sandbox/       # Docker 沙箱管理（docker、manager、client）
├── session/       # 会话管理（session、compaction、todo、instruction）
├── skill/         # 技能系统（discovery、执行）
├── snapshot/      # Git snapshot 快照
├── storage/       # 文件持久化存储
├── tool/          # 18个内置工具（bash、read、write、edit、glob、grep 等）
├── main.py        # FastAPI 入口（uvicorn main:app）
├── pyproject.toml # 依赖和构建配置
├── .env           # 环境变量
└── openbox.json   # LLM/Provider/Permission 配置
```

## 导入路径

所有 Python 导入改为扁平路径：
```python
# 之前
from openbox.core.config import get_config
from openagent.agent.loop import run_loop
from app.core.docker_manager import docker_manager

# 之后
from core.config import get_config
from agent.loop import run_loop
from sandbox.docker import docker_manager
```

## 核心模块说明

### Agent Loop (`agent/loop.py`)
Agent 主循环，负责：
- 管理 LLM 多轮对话（while loop，直到 finish_reason=stop）
- 处理工具调用（tool_call → execute → tool_result → 下一轮）
- 通过 bus 发布实时 SSE 事件
- 自动标题生成、token 统计、snapshot 快照

### LLM 集成 (`agent/llm.py`)
使用 LiteLLM 统一调用各 LLM 提供商：
- 支持 100+ 模型（OpenAI、Anthropic、Azure、自定义 base_url 等）
- 流式输出（streaming）
- Provider 配置自动注入（api_key、base_url）
- 工具调用（function calling）在 streaming 中处理

### 权限系统 (`permission/permission.py`)
工具执行前的权限控制：
- 支持 `allow` / `deny` / `ask` 三种规则
- `ask` 模式通过 SSE 向前端请求用户授权
- 沙箱环境默认 `allow all`（工具在隔离容器中执行）
- 支持 doom loop 检测（同一调用重复3次自动拦截）

### 沙箱容器 (`sandbox/`)
- `docker.py`: Docker 容器生命周期管理
- `manager.py`: 会话 → 容器的映射和复用
- `client.py`: HTTP 客户端，与容器内 action_server 通信

### 事件总线 (`bus/`)
进程内 async pub/sub：
- `publish(event_type, data)` 发布事件
- SSE endpoint 通过 `subscribe_all` 接收所有事件
- 事件类型：`session.status`、`message.text.delta`、`part.created`、`part.updated` 等

## 配置系统

### 环境变量 (`.env`)
```bash
OPENBOX_MODEL=openai/gpt-5.2        # LiteLLM 格式的模型名
OPENBOX_API_KEY=sk-xxx               # API Key（自动绑定到对应 provider）
OPENBOX_BASE_URL=https://proxy.com   # 自定义 API 地址
```

### JSON 配置 (`openbox.json`)
```json
{
  "model": "openai/gpt-5.2",
  "provider": {
    "openai": {
      "api_key": "sk-xxx",
      "base_url": "https://api.example.com"
    }
  },
  "permission": {
    "*": "allow"
  }
}
```

配置加载优先级：全局 `~/.config/openbox/openbox.json` → 项目级 `openbox.json` → 环境变量 → `OPENBOX_CONFIG_CONTENT`

### JSONC 支持
支持 `//` 和 `/* */` 注释（状态机解析器，不会破坏字符串内的 `https://` URL）。

## 沙箱 Action Server

容器内运行的 FastAPI 服务（`container/action_server.py`），提供：

| 端点 | 功能 |
|------|------|
| `POST /execute` | 执行 shell 命令 |
| `POST /execute_stream` | 流式执行（SSE） |
| `POST /write_file` | 写入文件 |
| `POST /read_file` | 读取文件（带行号） |
| `POST /glob` | 文件模式匹配 |
| `POST /grep` | 内容搜索 |
| `POST /list_files` | 列出目录 |
| `POST /upload` | 上传文件 |
| `GET /download` | 下载文件/目录 |
| `WS /terminal` | PTY 终端 WebSocket |

## API 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/agent/session` | POST/GET | 创建/列出会话 |
| `/api/agent/session/{id}` | GET/DELETE | 获取/删除会话 |
| `/api/agent/session/{id}/message` | GET | 获取消息列表 |
| `/api/agent/session/{id}/prompt_async` | POST | 异步发送消息（触发 agent loop） |
| `/api/agent/session/{id}/abort` | POST | 中止 agent |
| `/api/agent/event` | GET | SSE 实时事件流 |
| `/api/agent/permission/{id}/reply` | POST | 权限批准/拒绝 |
| `/api/agent/question/{id}/reply` | POST | 回答问题 |
| `/api/containers` | POST/GET | 创建/列出容器 |
| `/api/containers/{id}/terminal` | WS | 终端 WebSocket |

## 工具系统

18 个内置工具，全部在 Docker 沙箱内执行：

| 工具 | 功能 |
|------|------|
| `bash` | 执行 shell 命令 |
| `read` | 读取文件（带行号、offset/limit） |
| `write` | 写入文件 |
| `edit` | 精确字符串替换编辑 |
| `apply_patch` | 应用 unified diff patch |
| `glob` | 文件模式匹配搜索 |
| `grep` | 内容正则搜索 |
| `task` | 子任务调度 |
| `batch` | 批量执行 |
| `question` | 向用户提问 |
| `todo_write` / `todo_read` | 任务列表管理 |
| `plan_enter` / `plan_exit` | 计划模式 |
| `skill` | 调用技能 |
| `web_fetch` / `web_search` | Web 访问 |

## 测试验证

### 已通过的测试

| # | 测试项 | 结果 |
|---|--------|------|
| 1 | 服务启动 | 无 import 错误，18 工具注册 |
| 2 | Health API | `{"status":"ok","version":"0.1.0"}` |
| 3 | Session CRUD | 创建/列出/获取/删除 全部正常 |
| 4 | LLM 单轮问答 | `2+2=4`，token 统计正常 |
| 5 | LLM 多轮对话 | 上下文保持（记住 "Alice"） |
| 6 | LLM 流式输出 | 13 chunks，`1,2,3,4,5` |
| 7 | Agent Loop | 消息 → LLM → 流式回复 → 保存 |
| 8 | SSE 事件流 | 15 个实时事件正确推送 |
| 9 | 工具调用（write） | sandbox 写入文件成功 |
| 10 | 工具调用（bash） | sandbox 执行命令成功 |
| 11 | 端到端财务分析 | 写入 CSV → 写入 Python 脚本 → 执行分析 → 输出结果 |

### 端到端测试结果（财务数据分析）

输入 2024 年 Q1-Q4 模拟财务数据，Agent 自动：
1. 写入 `finance_2024.csv`
2. 生成 `analyze.py` 分析脚本
3. 在沙箱中执行，输出：

```
季度  营收      毛利率   净利润率  收入环比   利润环比
Q1   4520.00   40.00%   6.50%    -         -
Q2   5180.00   40.00%   8.01%   14.60%    41.16%
Q3   4890.00   40.00%   7.57%   -5.60%   -10.84%
Q4   6210.00   40.00%   8.52%   26.99%    42.97%

全年：总收入 20800 / 总成本 12480 / 总净利润 1608
```

## 修复的 Bug

| Bug | 文件 | 修复 |
|-----|------|------|
| `provider_kwargs` 未定义 | `agent/llm.py` | 添加 `_get_provider_kwargs()` 调用 |
| Pydantic AI 不兼容自定义 base_url | `agent/llm.py` | 统一走 LiteLLM direct path |
| 标题生成硬编码 anthropic 模型 | `agent/loop.py` | 改用 `config.model` |
| session.model 为空时 fallback 错误 | `agent/loop.py` | 改为 `session.model or config.model` |
| JSONC 注释解析破坏 `https://` URL | `core/config.py` | 状态机解析器 |
| `.env` 未自动加载 | `main.py` | 添加 `python-dotenv` |
| `await get_config()` 调用同步函数 | 6个文件 | 移除 `await` |
| 权限系统默认 "ask" 导致工具卡死 | `agent/loop.py` | sandbox 环境默认 allow all |
| 容器镜像缺少文件操作端点 | `container/action_server.py` | 重建镜像 |
| `MessageWithParts` 缺少 tokens 字段 | `models/message.py` | 添加字段 |

## 依赖

```toml
[project]
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "docker>=7.0.0",
    "httpx>=0.27.0",
    "websockets>=13.0",
    "pydantic>=2.0.0",
    "python-multipart>=0.0.12",
    "aiofiles>=24.0.0",
    "litellm>=1.40.0",
    "pydantic-ai>=0.1.0",
    "python-ulid>=3.0.0",
    "sse-starlette>=2.0.0",
    "python-frontmatter>=1.1.0",
    "pyyaml>=6.0.0",
    "python-dotenv>=1.0.0",
]
```

## 启动方式

```bash
cd backend
cp .env.example .env        # 配置环境变量
# 编辑 .env，设置 OPENBOX_MODEL / OPENBOX_API_KEY / OPENBOX_BASE_URL

uv run uvicorn main:app --host 0.0.0.0 --port 8080
```
