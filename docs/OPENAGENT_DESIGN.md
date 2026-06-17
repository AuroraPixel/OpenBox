# OpenAgent: Python 通用 Agent 框架实现方案

基于 OpenCode 的架构设计，用 Python 重写一个精简版通用 AI Agent。

**底层技术选型**：
- **Pydantic AI**：工具执行循环 + 类型安全（替代 Vercel AI SDK）
- **LiteLLM**：100+ LLM 供应商统一接入
- **FastAPI**：HTTP API 服务
- **OpenBox**：Docker 沙箱执行环境（所有工具在沙箱内执行）

**架构分层**：
```
┌─────────────────────────────────────────┐
│  OpenAgent API (FastAPI, 宿主机)          │
│  Agent 编排、权限、Skill、MCP、Session     │
├──────────────┬──────────────────────────┤
│ Pydantic AI  │  OpenBox 沙箱            │
│ 工具调用循环  │  bash/read/write/edit/   │
│ + LiteLLM    │  glob/grep 全部在沙箱执行 │
└──────────────┴──────────────────────────┘
                     │
              Docker Container
              (action_server.py)
```

**执行边界**：

| 工具/模块 | 执行位置 | 原因 |
|-----------|---------|------|
| bash, read, write, edit, apply_patch, glob, grep | **沙箱** | 文件/命令操作必须隔离 |
| MCP 工具调用 | **宿主机** | MCP 服务器是独立进程 |
| Skill 加载（读 SKILL.md） | **宿主机** | 读配置文件，无安全风险 |
| Skill 执行（LLM 按指令行动） | **沙箱** | 实际操作走 bash/write 等工具 |
| web_fetch, web_search | **宿主机** | 网络请求 |
| Plugin 代码 + hooks | **宿主机** | 认证、参数修改等宿主机逻辑 |
| Plugin `shell.env` | **注入到沙箱** | 环境变量传给沙箱内命令 |
| Plugin 注册的自定义工具 | **默认宿主机** | 多数调外部 API；可配 `sandbox=True` 走沙箱 |
| question, todo, plan, batch | **宿主机** | 纯逻辑工具，不涉及文件/命令 |
| Agent 编排、权限、事件总线 | **宿主机** | 控制面逻辑 |

**沙箱策略**：每个 Session 独占一个沙箱，创建 Session 时自动创建 Docker 容器，Session 结束时销毁。

---

## 目录

1. [项目结构](#项目结构)
2. [核心模块设计](#核心模块设计)
   - [Agent 循环](#1-agent-循环-agentlooppy)
   - [工具执行钩子](#2-工具执行钩子-agenthookspy)
   - [LLM 封装](#3-llm-封装-agentllmpy--pydantic-ai--litellm)
   - [工具系统](#4-工具系统-tooltoolpy--toolregistrypy)
   - [补充模块](#5-补充的关键模块)
3. [上下文管理与记忆管理（源码级详解）](#上下文管理与记忆管理源码级详解)
   - [三层存储模型](#三层存储模型)
   - [主循环与上下文加载](#主循环与上下文加载-agentlooppy--sessioncompactionpy)
   - [Compaction：上下文压缩](#compaction上下文压缩)
   - [Pruning：工具输出裁剪](#pruning工具输出裁剪)
   - [工具输出截断](#工具输出截断-tooltruncationpy)
   - [消息格式转换](#消息格式转换-sessionmessagepy)
   - [Prompt Caching](#prompt-caching)
   - [Instruction Files — 长期记忆](#instruction-files--长期记忆)
   - [系统提示组装](#系统提示组装)
   - [Session Summary](#session-summary)
   - [Processor 流式处理与重试](#processor-流式处理与重试)
   - [关键常量汇总](#关键常量汇总)
   - [完整数据流时序图](#完整数据流时序图)
4. [权限系统](#6-权限系统-permissionpermissionpy)
5. [Skill 系统](#7-skill-系统-skillskillpy)
6. [MCP 集成](#8-mcp-集成-mcpclientpy)
7. [HTTP API 端点](#9-http-api-端点)
8. [配置文件格式](#10-配置文件格式-openagentjson)
9. [依赖](#依赖)
10. [实现顺序](#实现顺序)
11. [暂不实现](#暂不实现后续迭代)
12. [验证方式](#验证方式)

---

## 项目结构

```
openagent/
  pyproject.toml
  openagent/
    __init__.py
    __main__.py                    # 入口：启动 uvicorn

    config/
      config.py                    # 配置加载、校验、合并
      markdown.py                  # YAML frontmatter 解析（用于 Skill）

    agent/
      agent.py                     # Agent 定义（build, explore, general 等）
      loop.py                      # 核心 Agent 外层循环（多轮编排、compaction、max steps）
      llm.py                       # Pydantic AI + LiteLLM 封装（单轮工具循环由框架处理）
      hooks.py                     # 工具执行钩子（权限检查、doom loop、事件推送）
      retry.py                     # 指数退避重试（2s 底数，2x 增长，30s 封顶）
      compaction.py                # 上下文溢出检测 + 自动摘要

    session/
      session.py                   # Session CRUD
      message.py                   # Message/Part Pydantic 模型
      status.py                    # Session 状态追踪（idle/busy/retry）
      revert.py                    # 按消息粒度撤销 LLM 修改
      todo.py                      # 会话级任务列表存储
      compaction.py                # 对话压缩 + 旧工具输出裁剪（pruning）

    tool/
      tool.py                      # Tool 基类 + define_tool() 工厂
      registry.py                  # 工具注册表：内置 + 自定义 + MCP
      truncation.py                # 输出截断（2000行 / 50KB）
      invalid.py                   # 错误恢复：LLM 调错工具时返回友好提示
      bash.py                      # 执行 Shell 命令
      read.py                      # 读文件（带行号）
      write.py                     # 写文件
      edit.py                      # 查找替换编辑
      apply_patch.py               # 结构化补丁：原子性多文件修改
      glob_tool.py                 # 文件名模式搜索
      grep.py                      # 文件内容搜索
      task.py                      # 子 Agent 派发
      batch.py                     # 并行工具调用（最多 25 个同时执行）
      skill.py                     # Skill 加载工具
      question.py                  # LLM 向用户提问（多选/文本）
      todo.py                      # 会话内任务跟踪（TodoWrite/TodoRead）
      plan.py                      # Plan 模式切换（PlanEnter/PlanExit）
      web_fetch.py                 # 网页抓取
      web_search.py                # 网页搜索

    skill/
      skill.py                     # Skill 发现与加载
      discovery.py                 # 远程 Skill 索引拉取

    mcp/
      client.py                    # MCP 客户端（stdio + HTTP/SSE）

    permission/
      permission.py                # 规则求值、ask/reply、通配符匹配

    question/
      question.py                  # 用户问答管理（LLM 提问 → SSE → 用户回答）

    snapshot/
      snapshot.py                  # 文件快照（基于 git）：track/restore/diff

    project/
      project.py                   # 项目发现（git root → 项目 ID）
      instance.py                  # 运行时上下文（工作目录、项目边界）

    shell/
      shell.py                     # Shell 选择 + 进程树 kill

    command/
      command.py                   # 命令模板（斜杠命令 /init /review 等）

    sandbox/
      manager.py                   # 沙箱生命周期管理（创建/销毁/复用）
      client.py                    # 沙箱 Action Server HTTP 客户端
      pool.py                      # Session ↔ Sandbox 映射管理

    server/
      app.py                       # FastAPI 应用、中间件、CORS
      routes/
        session.py                 # /session/* CRUD + 发送消息
        event.py                   # /event SSE 实时事件流
        permission.py              # /permission/* 权限应答
        config.py                  # /config 配置查询
        agent.py                   # /agent 列表
        skill.py                   # /skill 列表
        mcp.py                     # /mcp 状态与连接管理

    bus/
      bus.py                       # 进程内异步 pub/sub 事件总线
      events.py                    # 事件类型定义

    storage/
      storage.py                   # 文件系统 JSON 存储

    util/
      log.py                       # 结构化日志
      identifier.py                # ULID ID 生成
      wildcard.py                  # 通配符匹配（用于权限规则）
```

---

## 核心模块设计

### 1. Agent 循环 (`agent/loop.py`)

对应 OpenCode 的 `session/prompt.ts` 的 `loop()` 函数，是整个系统的心脏：

```python
async def loop(session_id: str) -> MessageWithParts:
    step = 0
    while True:
        if abort.is_set():
            break

        messages = await load_messages(session_id, filter_compacted=True)
        last_user, last_assistant = scan_messages(messages)

        # 终止条件：LLM 以文本结束（不是 tool_calls）
        if (last_assistant and last_assistant.finish
            and last_assistant.finish not in ("tool_calls", "unknown")
            and last_user.id < last_assistant.id):
            break

        step += 1

        # 上下文溢出 → 自动压缩
        if last_assistant and await is_overflow(last_assistant.tokens, model):
            await create_compaction(session_id)
            continue

        # 最大步数限制
        if step >= agent.max_steps:
            # 注入提示：要求 LLM 仅输出文本总结
            pass

        # 正常 LLM 调用
        tools = await resolve_tools(agent, model)
        result = await processor.process(system=system, messages=messages, tools=tools)

        if result == "stop": break
        if result == "compact": await create_compaction(session_id); continue
        # result == "continue" → 下一轮（工具结果已在消息中）
```

### 2. 工具执行钩子 (`agent/hooks.py`)

Pydantic AI 管理单轮内的工具调用循环，但我们需要在工具执行前后注入自定义逻辑：

```python
class ToolHooks:
    """包装每个工具的 execute 函数，注入权限、doom loop、事件推送等逻辑"""

    def __init__(self, session_id: str, bus: EventBus):
        self.session_id = session_id
        self.bus = bus
        self.call_history: list[tuple[str, str]] = []  # (tool_name, args_json)

    async def wrap_execute(self, tool_id: str, original_fn, args, ctx):
        # 1. 权限检查
        await permission.ask(permission=tool_id, patterns=[...], ...)

        # 2. Doom loop 检测（连续 3 次相同调用）
        call_sig = (tool_id, json.dumps(args, sort_keys=True))
        self.call_history.append(call_sig)
        if (len(self.call_history) >= 3
            and self.call_history[-1] == self.call_history[-2] == self.call_history[-3]):
            await permission.ask(permission="doom_loop", ...)

        # 3. 发布 SSE 事件：工具开始执行
        self.bus.publish("tool.running", {"tool": tool_id, "args": args})

        # 4. 执行
        result = await original_fn(args, ctx)

        # 5. 发布 SSE 事件：工具执行完成
        self.bus.publish("tool.completed", {"tool": tool_id, "output": result.output})

        return result
```

**重试逻辑**仍在 `agent/retry.py` 中，包装 Pydantic AI 的 agent.run() 调用：
- 可重试错误（429/503/overloaded）→ 指数退避（2s, 4s, 8s, 16s, 30s 封顶）
- Pydantic AI 自身也有参数校验自动重试（retries 参数）

### 3. LLM 封装 (`agent/llm.py`) — Pydantic AI + LiteLLM

使用 Pydantic AI 作为工具执行引擎，LiteLLM 作为供应商桥接：

```python
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.litellm import LiteLLMModel

def create_pydantic_agent(agent_def: AgentDef, tools: list[ToolInfo]) -> PydanticAgent:
    """根据 Agent 定义创建 Pydantic AI Agent 实例"""
    model = LiteLLMModel(agent_def.model)  # e.g. "anthropic/claude-sonnet-4-20250514"

    pa_agent = PydanticAgent(
        model,
        system_prompt=agent_def.prompt,
        retries=3,                         # 自动纠错重试
    )

    # 注册所有工具（内置 + 自定义 + MCP）
    for tool in tools:
        pa_agent.tool(tool.execute, name=tool.id, description=tool.description)

    return pa_agent
```

**Pydantic AI 自动处理的部分**（我们不需要自己写）：
- 工具调用循环：LLM → tool_calls → 执行 → 结果回传 → 再调 LLM
- 多 tool_calls 并行执行
- 流式响应解析和归一化
- 输入参数类型校验 + 自动纠错（LLM 传错参数时自动解释错误并重试）
- 不同供应商的协议差异（通过 LiteLLM 桥接）

**我们在外层控制的部分**（Pydantic AI 不管的）：
- 多轮会话编排（Agent 循环的 while True）
- 权限检查（在工具 execute 内部调用 permission.ask()）
- Doom loop 检测（在工具 execute 的 hook 中统计）
- 上下文压缩（compaction）触发
- 事件总线推送（tool 执行前后发布 SSE 事件）
- 最大步数限制

```python
# agent/loop.py — 外层循环仍然由我们控制
async def loop(session_id: str) -> MessageWithParts:
    step = 0
    while True:
        messages = await load_messages(session_id)
        if should_stop(messages): break

        step += 1
        if step >= agent.max_steps: break

        pa_agent = create_pydantic_agent(agent_def, tools)

        # Pydantic AI 自动处理单轮内的工具循环（包括并行执行）
        # 我们通过 message_history 实现多轮
        async with pa_agent.run_stream(
            user_prompt=last_user_message,
            message_history=to_pydantic_messages(messages),
        ) as result:
            async for chunk in result.stream_text(delta=True):
                bus.publish("message.text_delta", {"text": chunk})

            # 单轮结束后检查
            usage = result.usage()
            if await is_overflow(usage, model):
                await create_compaction(session_id)
                continue

            await store_result(session_id, result)

            if result.is_complete:  # LLM 没有更多工具调用
                break
```

**切换供应商只改一行**：
```python
model = LiteLLMModel("openai/gpt-4o")          # OpenAI
model = LiteLLMModel("anthropic/claude-sonnet-4-20250514")  # Claude
model = LiteLLMModel("deepseek/deepseek-chat")  # DeepSeek
model = LiteLLMModel("groq/llama-3.1-70b")      # Groq
model = LiteLLMModel("bedrock/claude-sonnet")    # AWS Bedrock
```

### 4. 工具系统 (`tool/tool.py` + `tool/registry.py`)

每个工具用 Pydantic 定义参数 Schema，统一包装验证和截断：

```python
class ToolResult(BaseModel):
    title: str
    output: str
    metadata: dict[str, Any] = {}

def define_tool(tool_id: str, *, description: str, parameters: type[BaseModel],
                execute: Callable) -> ToolInfo:
    """工厂函数，自动添加输入验证 + 输出截断"""
    async def wrapped_execute(args: dict, ctx: ToolContext) -> ToolResult:
        validated = parameters.model_validate(args)      # Pydantic 校验
        result = await execute(validated, ctx)
        truncated = truncate_output(result.output)       # 2000行/50KB 截断
        return ToolResult(title=result.title, output=truncated.content,
                          metadata={**result.metadata, "truncated": truncated.is_truncated})
    ...
```

工具注册表 (`registry.py`) 合并三类来源：
1. **内置工具**：bash, read, write, edit, glob, grep, task, skill, web_fetch, web_search
2. **自定义工具**：扫描 `.openagent/tools/*.py`，动态 import
3. **MCP 工具**：从已连接的 MCP 服务器获取，名称加前缀 `{server}_{tool}`

### 5. 补充的关键模块

#### 5.1 Batch Tool (`tool/batch.py`) — 并行工具调用

LLM 一次发起多个工具调用并行执行，大幅减少循环轮次：

```python
class BatchArgs(BaseModel):
    invocations: list[Invocation]  # 最多 25 个

class Invocation(BaseModel):
    tool: str         # 工具 ID
    parameters: dict  # 工具参数

async def execute(args: BatchArgs, ctx: ToolContext) -> ToolResult:
    # 校验：不能递归调用 batch 自身
    tasks = []
    for inv in args.invocations:
        tool_def = registry.get(inv.tool)
        tasks.append(tool_def.execute(inv.parameters, ctx))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # 合并结果返回
```

#### 5.2 Question Tool (`tool/question.py`) — LLM 主动提问

LLM 向用户提结构化问题，等待回答后继续：

```python
class QuestionArgs(BaseModel):
    questions: list[Question]  # 1-4 个问题

class Question(BaseModel):
    question: str
    options: list[Option]      # 2-4 个选项
    multi_select: bool = False

async def execute(args, ctx):
    # 发布 SSE 事件 → 客户端展示问题 → 用户回答 → 通过 REST API 回传
    request_id = generate_id()
    event = asyncio.Event()
    pending_questions[request_id] = PendingQuestion(event, ...)
    bus.publish("question.asked", {...})
    await event.wait()
    return ToolResult(output=pending_questions[request_id].answer)
```

#### 5.3 Todo 系统 (`session/todo.py` + `tool/todo.py`)

会话内任务跟踪，LLM 用来规划多步任务：

```python
class TodoItem(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed"]
    priority: Literal["high", "medium", "low"] = "medium"

# TodoWriteTool: LLM 创建/更新 todo
# TodoReadTool: LLM 读取当前 todo 列表
# 存储在 session 级别，通过 bus 事件推送更新
```

#### 5.4 Plan 模式 (`tool/plan.py`)

Agent 在"构建"和"规划"模式间切换：
- `plan_enter`: 切到 plan agent（只读，只能编辑 `.openagent/plans/*.md`）
- `plan_exit`: 切回 build agent（有完整编辑权限）
- 防止 LLM 在思考阶段误改代码

#### 5.5 Apply Patch Tool (`tool/apply_patch.py`)

结构化补丁格式，支持原子性多文件修改：

```
*** Begin Patch
*** Update File: src/main.py
@@@ context_before @@@
-old_line
+new_line
@@@ context_after @@@
*** Add File: src/new_file.py
+content here
*** Delete File: src/old_file.py
*** End Patch
```

4 轮渐进匹配：精确 → 右 trim → 全 trim → Unicode 归一化

#### 5.6 Invalid Tool (`tool/invalid.py`) — 错误恢复

LLM 调用不存在的工具或传错参数时，不崩溃，路由到 invalid tool：

```python
async def execute(args, ctx):
    return ToolResult(
        output=f"Tool '{args.tool}' not found. Available tools: {list_tools()}. "
               f"Error: {args.error}"
    )
```

在 `agent/llm.py` 中处理工具名修复：
1. 先尝试大小写修正（`Read` → `read`）
2. 修不了则路由到 invalid tool

#### 5.7 Snapshot + Revert (`snapshot/snapshot.py` + `session/revert.py`)

基于 git 的文件快照系统：
- 每个 Agent step 前后各记录一次快照（`git write-tree`）
- 支持按消息粒度撤销（`POST /session/{id}/revert`）
- 支持 unrevert（恢复被撤销的修改）
- 独立 git 仓库存储，不污染用户项目

#### 5.8 Compaction Pruning (`session/compaction.py`)

在 LLM 摘要压缩之外，还有工具输出裁剪：
- 从旧到新遍历工具输出
- 保护最近 40K token 的工具结果不被裁剪
- 更早的工具输出替换为 "[pruned]"
- 特定工具（如 skill）永不裁剪

#### 5.9 Project 发现 (`project/project.py`)

- 从 git root commit hash 推导稳定项目 ID
- 管理项目元数据（名称、工作目录、沙箱）
- `instance.py` 提供运行时上下文，判断路径是否在项目边界内

#### 5.10 Shell 集成 (`shell/shell.py`)

```python
def preferred_shell() -> str:
    """智能选择 shell，排除不兼容的（fish, nu）"""

async def kill_tree(pid: int):
    """进程树 kill：先 SIGTERM，超时后 SIGKILL"""
```

#### 5.11 沙箱集成 (`sandbox/`)

每个 Session 独占一个 Docker 沙箱，所有文件/命令操作在沙箱内执行。

**沙箱管理器** (`sandbox/manager.py`)：

```python
class SandboxManager:
    """管理 Session 与 Docker 沙箱的绑定关系"""

    def __init__(self, openbox_url: str = "http://localhost:8080"):
        self.openbox_url = openbox_url
        self._session_map: dict[str, SandboxInfo] = {}  # session_id → sandbox

    async def acquire(self, session_id: str) -> SandboxInfo:
        """为 Session 创建一个新沙箱（如果还没有）"""
        if session_id in self._session_map:
            return self._session_map[session_id]

        # 调用 OpenBox API 创建容器
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.openbox_url}/api/containers", json={
                "name": f"agent-{session_id[:8]}",
                "image": "openbox-sandbox:latest",
            })
            info = resp.json()

        sandbox = SandboxInfo(
            container_id=info["id"],
            port=info["port"],
            api_key=info["api_key"],
            session_id=session_id,
        )
        self._session_map[session_id] = sandbox
        return sandbox

    async def release(self, session_id: str):
        """Session 结束时销毁沙箱"""
        sandbox = self._session_map.pop(session_id, None)
        if sandbox:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"{self.openbox_url}/api/containers/{sandbox.container_id}"
                )
```

**沙箱客户端** (`sandbox/client.py`)：

```python
class SandboxClient:
    """封装对沙箱内 Action Server 的所有操作"""

    def __init__(self, host: str, port: int, api_key: str):
        self.base_url = f"http://{host}:{port}"
        self.headers = {"X-API-Key": api_key}

    async def execute(self, command: str, timeout: int = 120,
                      workdir: str = "/workspace") -> ExecuteResult:
        """执行命令 → bash 工具用这个"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/execute",
                json={"command": command, "timeout": timeout, "workdir": workdir},
                headers=self.headers, timeout=timeout + 10)
            data = resp.json()
            return ExecuteResult(
                exit_code=data["exit_code"],
                stdout=data["stdout"],
                stderr=data["stderr"],
            )

    async def write_file(self, path: str, content: str) -> None:
        """写文件 → write/edit 工具用这个"""
        file_bytes = content.encode("utf-8")
        async with httpx.AsyncClient() as client:
            await client.post(f"{self.base_url}/upload",
                files={"file": (os.path.basename(path), file_bytes)},
                data={"destination": os.path.dirname(path)},
                headers=self.headers)

    async def read_file(self, path: str) -> str:
        """读文件 → read 工具用这个"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/download",
                params={"path": path}, headers=self.headers)
            return resp.text

    async def list_files(self, path: str = "/workspace") -> list[FileEntry]:
        """列目录 → glob 工具用这个"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{self.base_url}/list_files",
                json={"path": path}, headers=self.headers)
            return [FileEntry(**f) for f in resp.json()["files"]]
```

**工具如何接入沙箱**：

每个工具的 `execute` 函数通过 `ToolContext` 拿到当前 Session 的 `SandboxClient`：

```python
# tool/bash.py
async def execute(args: BashArgs, ctx: ToolContext) -> ToolResult:
    sandbox = ctx.sandbox  # SandboxClient 实例
    result = await sandbox.execute(args.command, timeout=args.timeout)
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
    return ToolResult(title=f"exit code: {result.exit_code}", output=output)

# tool/read.py
async def execute(args: ReadArgs, ctx: ToolContext) -> ToolResult:
    content = await ctx.sandbox.read_file(args.file_path)
    # 加行号、截断等处理...
    return ToolResult(title=args.file_path, output=numbered_content)

# tool/write.py
async def execute(args: WriteArgs, ctx: ToolContext) -> ToolResult:
    await ctx.sandbox.write_file(args.file_path, args.content)
    return ToolResult(title=f"Wrote {args.file_path}", output="File written successfully")

# tool/grep.py
async def execute(args: GrepArgs, ctx: ToolContext) -> ToolResult:
    # grep 通过 bash 在沙箱内执行
    result = await ctx.sandbox.execute(
        f"grep -rn '{args.pattern}' {args.path}", timeout=30
    )
    return ToolResult(title=f"grep: {args.pattern}", output=result.stdout)

# tool/glob_tool.py
async def execute(args: GlobArgs, ctx: ToolContext) -> ToolResult:
    # 也通过 bash 执行 find 命令
    result = await ctx.sandbox.execute(
        f"find {args.path} -name '{args.pattern}' -type f | head -100", timeout=30
    )
    return ToolResult(title=f"glob: {args.pattern}", output=result.stdout)
```

**edit 和 apply_patch 工具的特殊处理**：

```python
# tool/edit.py — 需要先读、再改、再写
async def execute(args: EditArgs, ctx: ToolContext) -> ToolResult:
    # 1. 从沙箱读取文件
    content = await ctx.sandbox.read_file(args.file_path)
    # 2. 在宿主机内存中做替换（渐进式匹配逻辑）
    new_content = apply_edit(content, args.old_string, args.new_string)
    # 3. 写回沙箱
    await ctx.sandbox.write_file(args.file_path, new_content)
    return ToolResult(title=f"Edited {args.file_path}", output=diff)
```

**Session 生命周期与沙箱绑定**：

```python
# session/session.py
async def create_session(...) -> Session:
    session = Session(id=generate_id(), ...)
    # 创建 Session 时自动分配沙箱
    sandbox = await sandbox_manager.acquire(session.id)
    session.sandbox_id = sandbox.container_id
    return session

async def delete_session(session_id: str):
    # 删除 Session 时自动释放沙箱
    await sandbox_manager.release(session_id)
    await storage.delete(session_id)
```

#### 5.12 OpenBox Action Server 扩展

当前 Action Server 缺少 Agent 需要的操作，需要扩展以下端点。

**修改文件**：`/root/workspace/sendbox/OpenBox/container/action_server.py`

**a) 流式命令执行**（最关键的新增）：

```python
@app.post("/execute_stream")
async def execute_stream(req: ExecuteRequest):
    """流式执行命令，通过 SSE 实时推送 stdout/stderr"""
    process = await asyncio.create_subprocess_shell(
        req.command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=req.workdir or "/workspace",
    )

    async def event_generator():
        import asyncio as aio
        stdout_done = stderr_done = False
        try:
            while not (stdout_done and stderr_done):
                # 并行读取 stdout 和 stderr
                tasks = {}
                if not stdout_done:
                    tasks["stdout"] = aio.create_task(process.stdout.readline())
                if not stderr_done:
                    tasks["stderr"] = aio.create_task(process.stderr.readline())

                done, _ = await aio.wait(tasks.values(), return_when=aio.FIRST_COMPLETED)
                for name, task in tasks.items():
                    if task in done:
                        line = task.result()
                        if not line:
                            if name == "stdout": stdout_done = True
                            else: stderr_done = True
                        else:
                            yield {"event": "output", "data": json.dumps({
                                "type": name,
                                "content": line.decode(errors="replace"),
                            })}
                    else:
                        task.cancel()

            exit_code = await aio.wait_for(process.wait(), timeout=req.timeout or 120)
        except aio.TimeoutError:
            process.kill()
            exit_code = -1
            yield {"event": "output", "data": json.dumps({
                "type": "system",
                "content": f"Command terminated: timeout {req.timeout}s exceeded\n",
            })}

        yield {"event": "exit", "data": json.dumps({
            "exit_code": exit_code,
            "timed_out": exit_code == -1,
        })}

    return EventSourceResponse(event_generator())
```

**b) 文件操作端点**：

```python
@app.post("/write_file")   # 直接写文件内容（比 upload multipart 更方便）
@app.post("/read_file")    # 读文件（带行号、偏移、限制）
@app.post("/glob")         # 文件名模式匹配（fnmatch）
@app.post("/grep")         # 文件内容搜索（调用 grep -rn）
```

**c) 通讯链路**：

```
LLM 调用 bash 工具
  │
  ▼ OpenAgent bash.py (宿主机)
  │
  ├─ 权限检查 → permission.ask()
  │
  ├─ HTTP POST → sandbox:8000/execute_stream (SSE)
  │     ← event: output  {"type":"stdout","content":"Installing pandas...\n"}
  │     ← event: output  {"type":"stdout","content":"Successfully installed\n"}
  │     ← event: exit    {"exit_code": 0}
  │         │
  │         └─ 每个 chunk → ctx.metadata() → Bus → SSE → UI 实时显示
  │
  ├─ 组装完整 output → truncation（>2000行/>50KB 截断存文件）
  │
  └─ 返回给 LLM: {output: "Installing pandas...\nSuccessfully installed\n", exit_code: 0}
```

**d) 超时和卡住处理**：

| 场景 | 处理方式 |
|------|---------|
| 命令超时（死循环等） | Action Server `wait_for` 超时 → kill 进程 → 返回已有输出 + 超时标记 |
| 交互式命令（vim 等） | stdin 无输入源 → 挂起 → 超时被杀 → LLM 收到超时提示 |
| 长命令（npm install） | SSE 流式推送每行输出 → UI 实时可见 → LLM 可指定更长 timeout |
| 用户取消 | abort signal → 关闭 HTTP 连接 → Action Server 检测断连 → 杀进程 |
| 沙箱崩溃 | HTTP 断开 → SandboxClient 异常 → 返回错误给 LLM |
| 系统提示防范 | 提示词明确禁止交互式命令（git rebase -i、vim 等） |

**e) `shell.env` Plugin hook 如何注入到沙箱**：

```python
# sandbox/client.py
async def execute_stream(self, command: str, env: dict = None, ...):
    """env 参数合并 plugin shell.env hook 的环境变量"""
    payload = {"command": command, "timeout": timeout, "env": env or {}}
    # Action Server 在执行命令时注入这些环境变量
```

#### 5.13 Command 模板 (`command/command.py`)

预定义命令模板，支持变量替换：
```yaml
# .openagent/commands/review.md
---
name: review
description: Review code changes
agent: build
---
Review the following changes: $ARGUMENTS
```

---

## 上下文管理与记忆管理（源码级详解）

> 以下内容基于 OpenCode 源码的逐行分析，覆盖每个函数、每个常量、每个数据流。
> 对应 OpenCode 源文件：`session/prompt.ts`, `session/compaction.ts`, `session/message-v2.ts`,
> `session/instruction.ts`, `session/summary.ts`, `session/processor.ts`, `session/llm.ts`,
> `session/retry.ts`, `tool/truncation.ts`, `util/token.ts`, `provider/transform.ts`,
> `provider/error.ts`, `storage/storage.ts`, `session/system.ts`

### 三层存储模型

```
~/.local/share/opencode/storage/
├── session/{projectID}/{sessionID}.json      # Session 元数据
├── message/{sessionID}/{messageID}.json      # 消息（User / Assistant）
├── part/{messageID}/{partID}.json            # Part（消息的组成单元）
├── session_diff/{sessionID}.json             # Git diff 汇总
├── todo/{sessionID}.json                     # 会话级任务列表
└── migration                                  # 迁移版本号
```

**Session** 包含 `id, projectID, title, summary(additions/deletions/files), parentID(分叉), permission`。

**Message** 分两种角色：

| 字段 | User | Assistant |
|------|------|-----------|
| role | `"user"` | `"assistant"` |
| 关键字段 | `agent, model, format, system, variant, tools` | `parentID, modelID, providerID, tokens, cost, summary, error, finish, structured` |
| tokens | — | `{ total?, input, output, reasoning, cache: { read, write } }` |

**Part** 有 12 种类型：`text, reasoning, tool, file, step-start, step-finish, snapshot, patch, agent, retry, compaction, subtask`。

其中 `ToolPart` 的 `state` 是核心：

```python
class ToolStateCompleted(BaseModel):
    status: Literal["completed"]
    input: dict
    output: str
    title: str
    metadata: dict
    time: TimeWithCompacted  # { start, end, compacted? }  ← compacted 用于 pruning
    attachments: list[FilePart] | None
```

`time.compacted` 被设置后，该工具输出在发给 LLM 时会被替换为 `"[Old tool result content cleared]"`。

**Storage 操作**：

```python
class Storage:
    async def read(key: list[str]) -> T:       # 读锁 → 读 JSON
    async def write(key: list[str], content):  # 写锁 → 写 JSON
    async def update(key: list[str], fn):      # 写锁 → 读 → fn(draft) → 写回
    async def remove(key: list[str]):          # 删除文件
    async def list(prefix: list[str]):         # glob 扫描子目录
```

Python 复刻要点：用 `aiofiles` + `asyncio.Lock` 或 `filelock` 替代 Bun 的文件锁。

---

### 主循环与上下文加载 (`agent/loop.py` / `session/compaction.py`)

对应 OpenCode `session/prompt.ts` 的 `loop()` 函数 (line 276-722)，是整个系统的心脏。

#### 完整伪代码

```python
async def loop(session_id: str) -> MessageWithParts:
    step = 0
    while True:
        if abort.is_set():
            break

        # ① 加载消息——只加载最近一次 compaction 之后的
        msgs = await filter_compacted(stream_messages(session_id))

        # ② 向后扫描找关键消息
        last_user = None       # 最后一条 user 消息
        last_assistant = None  # 最后一条 assistant 消息
        last_finished = None   # 最后一条有 finish 的 assistant 消息
        tasks = []             # 尚未处理的 compaction/subtask parts
        for i in range(len(msgs) - 1, -1, -1):
            msg = msgs[i]
            if not last_user and msg.role == "user":
                last_user = msg
            if not last_assistant and msg.role == "assistant":
                last_assistant = msg
            if not last_finished and msg.role == "assistant" and msg.finish:
                last_finished = msg
            if last_user and last_finished:
                break
            # 收集未处理的 compaction/subtask parts
            for part in msg.parts:
                if part.type in ("compaction", "subtask") and not last_finished:
                    tasks.append(part)

        # ③ 终止判断：LLM 以文本结束（不是 tool_calls）
        if (last_assistant and last_assistant.finish
                and last_assistant.finish not in ("tool-calls", "unknown")
                and last_user.id < last_assistant.id):
            break

        step += 1

        # ④ 第一步时异步触发标题生成
        if step == 1:
            asyncio.create_task(ensure_title(session, last_user, msgs))

        task = tasks.pop() if tasks else None

        # ⑤ 处理待执行的 subtask（子 Agent 任务）
        if task and task.type == "subtask":
            await execute_subtask(task, session_id, last_user, msgs)
            continue

        # ⑥ 处理待执行的 compaction
        if task and task.type == "compaction":
            result = await compaction_process(msgs, last_user.id, abort, session_id, task.auto)
            if result == "stop":
                break
            continue

        # ⑦ 检测上下文溢出 → 自动触发 compaction
        if (last_finished
                and not last_finished.summary
                and await is_overflow(last_finished.tokens, model)):
            await compaction_create(session_id, last_user.agent, last_user.model, auto=True)
            continue

        # ⑧ 正常处理
        agent = await get_agent(last_user.agent)
        max_steps = agent.steps or float("inf")
        is_last_step = step >= max_steps

        # 注入 plan mode / agent 切换提示
        msgs = await insert_reminders(msgs, agent, session)

        # 包装 step>1 的后续用户消息为 <system-reminder>
        if step > 1 and last_finished:
            for msg in msgs:
                if msg.role != "user" or msg.id <= last_finished.id:
                    continue
                for part in msg.parts:
                    if part.type == "text" and not part.ignored and not part.synthetic:
                        part.text = (
                            "<system-reminder>\n"
                            "The user sent the following message:\n"
                            f"{part.text}\n\n"
                            "Please address this message and continue with your tasks.\n"
                            "</system-reminder>"
                        )

        # 构建系统提示
        system = [*await environment_prompt(model), *await instruction_system()]

        # 转换为 LLM 可消费的格式
        messages = to_model_messages(msgs, model)

        # 如果到了最大步数，注入提示要求 LLM 仅输出文本
        if is_last_step:
            messages.append({"role": "assistant", "content": MAX_STEPS_PROMPT})

        # 解析工具列表
        tools = await resolve_tools(agent, session, model, msgs)

        # 调用 LLM
        result = await processor.process(
            system=system, messages=messages, tools=tools, model=model
        )

        if result == "stop":
            break
        if result == "compact":
            await compaction_create(session_id, last_user.agent, last_user.model, auto=True)
        continue

    # 循环结束后：裁剪旧工具输出
    await compaction_prune(session_id)

    # 返回最后的 assistant 消息
    return last_assistant_message
```

#### filter_compacted 详解

对应 `message-v2.ts:736-751`，是上下文窗口管理的核心过滤器：

```python
async def filter_compacted(stream: AsyncIterable[MessageWithParts]) -> list[MessageWithParts]:
    """从新到旧遍历消息，遇到 compaction 边界就截断。
    边界定义：一条 user 消息有 compaction part，且其对应的 assistant 响应已完成（summary=True, finish 存在）
    """
    result = []
    completed = set()  # 已有完成响应的 compaction 用户消息 parentID

    async for msg in stream:  # stream 从新到旧
        result.append(msg)
        if (msg.role == "user"
                and msg.id in completed
                and any(p.type == "compaction" for p in msg.parts)):
            break  # 截断！更早的消息全部丢弃
        if (msg.role == "assistant" and msg.summary and msg.finish):
            completed.add(msg.parent_id)

    result.reverse()  # 恢复时间顺序（旧→新）
    return result
```

**关键行为**：compaction 后，LLM 只看到 `[compaction_user_msg, compaction_summary, ...后续新消息]`，之前的全部历史不可见。

---

### Compaction：上下文压缩

对应 `session/compaction.ts`，分为三步：溢出检测 → 创建请求 → 执行压缩。

#### 溢出检测 (`is_overflow`)

```python
COMPACTION_BUFFER = 20_000  # token

async def is_overflow(tokens: TokenUsage, model: ModelInfo) -> bool:
    config = await get_config()
    if config.compaction.auto is False:
        return False
    if model.limit.context == 0:
        return False

    # 本轮的总 token 消耗
    count = tokens.total or (tokens.input + tokens.output + tokens.cache_read + tokens.cache_write)

    # 预留 buffer
    reserved = config.compaction.reserved or min(COMPACTION_BUFFER, max_output_tokens(model))

    # 可用空间
    usable = (model.limit.input - reserved) if model.limit.input else (model.limit.context - max_output_tokens(model))

    return count >= usable
```

**计算公式**：`已用 token >= 可用 token` 时触发。其中：
- `可用 = min(input_limit, context_limit) - reserved_buffer`
- `reserved` 默认 = `min(20000, max_output_tokens)`

#### 创建 Compaction 请求 (`compaction_create`)

不是立即执行，而是创建一条特殊的 user 消息 + compaction part，下一轮循环检测到后执行：

```python
async def compaction_create(session_id: str, agent: str, model: ModelRef, auto: bool):
    msg = await update_message({
        "id": ascending_id("message"),
        "role": "user",
        "session_id": session_id,
        "model": model,
        "agent": agent,
    })
    await update_part({
        "id": ascending_id("part"),
        "message_id": msg.id,
        "session_id": session_id,
        "type": "compaction",
        "auto": auto,
    })
```

#### 执行压缩 (`compaction_process`)

```python
COMPACTION_PROMPT = """Provide a detailed prompt for continuing our conversation above.
Focus on information that would be helpful for continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're going to do next.
The summary that you construct will be used so that another agent can read it and continue the work.

When constructing the summary, try to stick to this template:
---
## Goal

[What goal(s) is the user trying to accomplish?]

## Instructions

- [What important instructions did the user give you that are relevant]
- [If there is a plan or spec, include information about it so next agent can continue using it]

## Discoveries

[What notable things were learned during this conversation that would be useful for the next agent to know when continuing the work]

## Accomplished

[What work has been completed, what work is still in progress, and what work is left?]

## Relevant files / directories

[Construct a structured list of relevant files that have been read, edited, or created that pertain to the task at hand. If all the files in a directory are relevant, include the path to the directory.]
---"""

async def compaction_process(messages, parent_id, abort, session_id, auto):
    user_message = find_message(messages, parent_id)

    # 1. 选择 compaction agent 的模型（可配置独立的小模型）
    agent = await get_agent("compaction")
    model = agent.model or user_message.model

    # 2. 创建 assistant 消息，标记 summary=True
    assistant_msg = await update_message({
        "role": "assistant",
        "summary": True,          # ← 关键标记，filter_compacted 靠这个识别
        "mode": "compaction",
        "agent": "compaction",
        # ... tokens, cost 等初始化为 0
    })

    # 3. 允许 plugin 替换压缩 prompt
    compacting = await plugin_trigger("experimental.session.compacting", ...)
    prompt_text = compacting.prompt or COMPACTION_PROMPT

    # 4. 将全部历史消息 + 压缩 prompt 发给 LLM
    #    注意：不给任何工具！不加系统提示！纯粹总结对话
    result = await processor.process(
        tools={},
        system=[],
        messages=[
            *to_model_messages(messages, model),  # 全部历史
            {"role": "user", "content": prompt_text},
        ],
        model=model,
    )

    # 5. 如果是自动触发的，注入 "Continue" 消息让循环继续
    if result == "continue" and auto:
        continue_msg = await update_message({"role": "user", ...})
        await update_part({
            "type": "text",
            "synthetic": True,
            "text": "Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.",
        })

    return "continue" or "stop"
```

**关键设计决策**：
- Compaction 时**不给 tools**，LLM 只能输出文本摘要
- Compaction 时**不加系统提示**，纯粹总结对话
- 自动 compaction 完成后注入合成 "Continue" 消息，让主循环继续

---

### Pruning：工具输出裁剪

对应 `compaction.ts:58-99`，是 compaction 之外的辅助策略。在主循环结束后执行。

```python
PRUNE_MINIMUM = 20_000    # token，低于此阈值不执行裁剪
PRUNE_PROTECT = 40_000    # token，保护最近这么多 token 的工具输出
PRUNE_PROTECTED_TOOLS = ["skill"]  # 永不裁剪的工具

async def compaction_prune(session_id: str):
    config = await get_config()
    if config.compaction.prune is False:
        return

    msgs = await get_all_messages(session_id)
    total = 0       # 已扫描的工具输出 token 数
    pruned = 0      # 需要裁剪的 token 数
    to_prune = []   # 待裁剪的 part 列表
    turns = 0       # 用户轮次计数

    # 从最新消息往回扫描
    for msg_index in range(len(msgs) - 1, -1, -1):
        msg = msgs[msg_index]
        if msg.role == "user":
            turns += 1
        if turns < 2:
            continue    # 跳过最近 2 轮用户消息的工具输出
        if msg.role == "assistant" and msg.summary:
            break       # 到 compaction 边界停止

        for part_index in range(len(msg.parts) - 1, -1, -1):
            part = msg.parts[part_index]
            if part.type == "tool" and part.state.status == "completed":
                if part.tool in PRUNE_PROTECTED_TOOLS:
                    continue
                if part.state.time.compacted:
                    break  # 已经裁剪过了，停止

                estimate = token_estimate(part.state.output)  # len(output) / 4
                total += estimate
                if total > PRUNE_PROTECT:    # 超过 40,000 token 保护线
                    pruned += estimate
                    to_prune.append(part)

    # 只有裁剪量 > 20,000 token 时才执行
    if pruned > PRUNE_MINIMUM:
        for part in to_prune:
            part.state.time.compacted = time.time() * 1000  # 毫秒时间戳
            await update_part(part)
```

**裁剪效果**：在 `to_model_messages()` 转换时：

```python
if part.state.time.compacted:
    output_text = "[Old tool result content cleared]"
    attachments = []
```

**设计意图**：不等到触发 compaction，就先把旧的工具输出清空，渐进式减少 token 消耗。

---

### 工具输出截断 (`tool/truncation.py`)

对应 `tool/truncation.ts`，在工具执行完毕后立即截断超长输出：

```python
MAX_LINES = 2000
MAX_BYTES = 50 * 1024  # 50KB
RETENTION_MS = 7 * 24 * 3600 * 1000  # 7 天
CLEANUP_INTERVAL = 3600 * 1000       # 每小时清理

async def truncate_output(text: str, options: TruncateOptions = None,
                          agent: AgentInfo = None) -> TruncateResult:
    max_lines = options.max_lines if options else MAX_LINES
    max_bytes = options.max_bytes if options else MAX_BYTES
    direction = options.direction if options else "head"  # head = 保留开头

    lines = text.split("\n")
    total_bytes = len(text.encode("utf-8"))

    # 未超限，直接返回
    if len(lines) <= max_lines and total_bytes <= max_bytes:
        return TruncateResult(content=text, truncated=False)

    # 按行和字节双重限制截取
    out = []
    bytes_count = 0
    hit_bytes = False

    if direction == "head":
        for i, line in enumerate(lines):
            if i >= max_lines:
                break
            size = len(line.encode("utf-8")) + (1 if i > 0 else 0)
            if bytes_count + size > max_bytes:
                hit_bytes = True
                break
            out.append(line)
            bytes_count += size
    # ... tail 方向类似

    # 保存完整输出到临时文件
    filepath = os.path.join(DATA_DIR, "tool-output", ascending_id("tool"))
    async with aiofiles.open(filepath, "w") as f:
        await f.write(text)

    # 提示 LLM 如何获取完整内容
    has_task = agent and has_task_tool(agent)
    hint = (
        f"Use the Task tool to have explore agent process this file with Grep and Read..."
        if has_task else
        f"Use Grep to search the full content or Read with offset/limit..."
    )

    removed = total_bytes - bytes_count if hit_bytes else len(lines) - len(out)
    unit = "bytes" if hit_bytes else "lines"
    preview = "\n".join(out)

    return TruncateResult(
        content=f"{preview}\n\n...{removed} {unit} truncated...\n\n{hint}",
        truncated=True,
        output_path=filepath,
    )
```

**清理机制**：注册定时任务，每小时运行一次，删除 7 天前的截断文件。

---

### Token 估算

```python
CHARS_PER_TOKEN = 4

def token_estimate(text: str) -> int:
    return max(0, round(len(text or "") / CHARS_PER_TOKEN))
```

极其简单的启发式方法。用于 pruning 中估算工具输出的 token 消耗。精度不需要很高，因为 pruning 的阈值本身留有余量。

---

### 消息格式转换 (`session/message.py`)

对应 `message-v2.ts:478-701` 的 `toModelMessages()`，将内部 `WithParts[]` 转为 LLM SDK 可消费的格式：

| 内部 Part 类型 | 转换规则 |
|:---|:---|
| `text` (非 ignored) | `{"type": "text", "text": "..."}` |
| `file` (非 text/plain) | `{"type": "file", "url": ..., "media_type": ..., "filename": ...}` |
| `compaction` | `{"type": "text", "text": "What did we do so far?"}` |
| `subtask` | `{"type": "text", "text": "The following tool was executed by the user"}` |
| `tool` (completed, 未裁剪) | tool-result 带完整 output |
| `tool` (completed, 已裁剪) | `output = "[Old tool result content cleared]"`, attachments 清空 |
| `tool` (pending/running) | `error_text = "[Tool execution was interrupted]"` |
| `tool` (error) | `error_text = part.state.error` |
| `reasoning` | `{"type": "reasoning", "text": "..."}` |
| assistant 有 error | **整条消息被跳过**（除非是 aborted 且有实质内容） |

**media 处理**：对于不支持 tool result 中带图片的 provider（非 Anthropic/OpenAI），图片被抽出来作为独立的 user 消息注入：

```python
if not supports_media_in_tool_results and media_attachments:
    result.append({
        "role": "user",
        "parts": [
            {"type": "text", "text": "Attached image(s) from tool result:"},
            *[{"type": "file", "url": a.url, "media_type": a.mime} for a in media_attachments],
        ]
    })
```

Python 复刻要点：Pydantic AI 有自己的消息格式，需要写一个 `to_pydantic_messages()` 适配层。

---

### Prompt Caching

#### Anthropic 缓存

对应 `provider/transform.ts:174-212`，只对 Anthropic/Claude 模型应用：

```python
def apply_caching(msgs: list[ModelMessage], provider_id: str) -> list[ModelMessage]:
    """给前 2 条系统消息 + 最后 2 条非系统消息添加 ephemeral cache 标记"""
    system_msgs = [m for m in msgs if m.role == "system"][:2]
    final_msgs = [m for m in msgs if m.role != "system"][-2:]

    cache_options = {
        "anthropic": {"cacheControl": {"type": "ephemeral"}},
        "bedrock": {"cachePoint": {"type": "default"}},
    }

    for msg in set(system_msgs + final_msgs):
        msg.provider_options = deep_merge(msg.provider_options or {}, cache_options)

    return msgs
```

**作用**：Anthropic 的 prompt caching 可以跨轮次复用系统提示和近期对话，显著降低 token 消耗和延迟。

#### OpenAI 缓存

```python
if provider_id == "openai" or provider_options.get("setCacheKey"):
    options["promptCacheKey"] = session_id  # 按会话级别缓存
```

---

### Instruction Files — 长期记忆

对应 `session/instruction.ts`，充当**跨会话持久记忆**。每轮 LLM 调用都会重新加载。

#### 系统级指令加载

```python
INSTRUCTION_FILES = ["AGENTS.md", "CLAUDE.md", "CONTEXT.md"]  # CONTEXT.md 已废弃

async def instruction_system() -> list[str]:
    """加载所有指令文件，返回内容列表"""
    paths = set()

    # 1. 项目级：从当前目录向上查找（找到第一个文件名匹配就停止）
    for filename in INSTRUCTION_FILES:
        matches = find_up(filename, current_dir, project_root)
        if matches:
            paths.update(matches)
            break  # 注意：AGENTS.md 找到后不再找 CLAUDE.md

    # 2. 全局级
    global_paths = [
        os.path.join(config_dir, "AGENTS.md"),    # ~/.config/opencode/AGENTS.md
        os.path.join(home, ".claude", "CLAUDE.md"),  # ~/.claude/CLAUDE.md
    ]
    for p in global_paths:
        if os.path.exists(p):
            paths.add(p)
            break  # 找到一个就停

    # 3. config.instructions[] 中的额外路径
    for instruction in config.instructions or []:
        if instruction.startswith("http://") or instruction.startswith("https://"):
            # URL：fetch 获取，5s 超时
            content = await fetch_url(instruction, timeout=5)
            results.append(f"Instructions from: {instruction}\n{content}")
            continue
        # 本地路径：支持 ~/ 展开、glob 模式
        for match in resolve_path(instruction):
            paths.add(match)

    # 读取所有文件
    results = []
    for p in paths:
        content = await read_file(p)
        if content:
            results.append(f"Instructions from: {p}\n{content}")
    return results
```

#### 目录级指令（Read 工具触发）

当 Read 工具读取某个文件时，自动查找该文件到项目根目录之间的所有指令文件：

```python
async def instruction_resolve(messages, filepath, message_id) -> list[InstructionFile]:
    """查找 filepath 所在目录到项目根之间的指令文件"""
    system_paths = await instruction_system_paths()  # 已加载的系统级指令
    already_loaded = instruction_loaded(messages)     # 已在消息中出现过的指令

    results = []
    current = os.path.dirname(os.path.abspath(filepath))
    root = os.path.abspath(project_dir)

    while current.startswith(root) and current != root:
        found = find_instruction_file(current)  # 在当前目录找 AGENTS.md/CLAUDE.md
        if (found
                and found not in system_paths    # 不是系统级的
                and found not in already_loaded  # 没有已加载过
                and not is_claimed(message_id, found)):  # 本消息内没有重复
            claim(message_id, found)  # 标记为已加载
            content = await read_file(found)
            if content:
                results.append(InstructionFile(
                    filepath=found,
                    content=f"Instructions from: {found}\n{content}"
                ))
        current = os.path.dirname(current)

    return results
```

**防重复机制**：
- `claims: dict[message_id, set[filepath]]` — 同一消息内不重复加载
- `loaded()` 函数扫描已有消息的 Read 工具结果，检查已加载过的指令
- `clear(message_id)` 在消息处理完成后清理

---

### 系统提示组装

对应 `session/system.ts` + `session/llm.ts`。

#### 环境信息

```python
async def environment_prompt(model) -> list[str]:
    return [
        f"You are powered by the model named {model.api_id}. "
        f"The exact model ID is {model.provider_id}/{model.api_id}\n"
        f"Here is some useful information about the environment you are running in:\n"
        f"<env>\n"
        f"  Working directory: {instance.directory}\n"
        f"  Is directory a git repo: {'yes' if project.vcs == 'git' else 'no'}\n"
        f"  Platform: {sys.platform}\n"
        f"  Today's date: {date.today().isoformat()}\n"
        f"</env>"
    ]
```

#### 基础 Prompt 选择

根据模型选择不同的基础 prompt：

| 模型匹配 | Prompt 文件 |
|:---|:---|
| `gpt-5` | `prompt/codex_header.txt` |
| `gpt-*`, `o1`, `o3` | `prompt/beast.txt` |
| `gemini-*` | `prompt/gemini.txt` |
| `claude` | `prompt/anthropic.txt` |
| 其他 | `prompt/qwen.txt` |

#### 完整组装

```python
async def build_system_prompt(agent, model, user_message, session_id):
    system = []

    # 第一部分：基础 prompt + 用户指令 + instruction files
    parts = [
        agent.prompt or provider_prompt(model),   # agent 自定义 prompt 或模型默认
        *await instruction_system(),               # instruction files 内容
        user_message.system or "",                 # 用户自定义 system prompt
    ]
    system.append("\n".join(filter(None, parts)))

    # Plugin 可以 transform system prompt
    system = await plugin_trigger("experimental.chat.system.transform", system=system)

    return system
```

**系统提示分为 2 部分**（环境信息独立一条），这对 Anthropic 的 cache control 很重要——前 2 条系统消息被标记为 ephemeral cache。

---

### Session Summary

对应 `session/summary.ts`，在每步处理完成后异步执行。

#### Session 级摘要

```python
async def summarize_session(session_id, messages):
    """计算整个 session 的 git diff 统计"""
    diffs = await compute_diff(messages)
    await session_update(session_id, lambda draft: setattr(draft, 'summary', {
        "additions": sum(d.additions for d in diffs),
        "deletions": sum(d.deletions for d in diffs),
        "files": len(diffs),
    }))
    await storage_write(["session_diff", session_id], diffs)
```

#### 消息级摘要 + 标题生成

```python
async def summarize_message(message_id, messages):
    """为用户消息生成 diff 和标题"""
    filtered = [m for m in messages
                if m.id == message_id or (m.role == "assistant" and m.parent_id == message_id)]
    diffs = await compute_diff(filtered)
    user_msg.summary = {"diffs": diffs}

    # 用 title agent + 小模型生成标题（<= 50 字符）
    if text_part and not user_msg.summary.get("title"):
        title_agent = await get_agent("title")
        small_model = await get_small_model(user_msg.model.provider_id) or user_msg.model
        stream = await llm_stream(
            agent=title_agent,
            model=small_model,
            messages=[{"role": "user", "content": f"The following is the text to summarize:\n<text>\n{text_part.text}\n</text>"}],
        )
        user_msg.summary["title"] = await stream.text()
```

#### compute_diff

```python
async def compute_diff(messages):
    """找最早的 step-start snapshot 和最晚的 step-finish snapshot，计算 git diff"""
    from_snapshot = None
    to_snapshot = None
    for msg in messages:
        for part in msg.parts:
            if part.type == "step-start" and part.snapshot and not from_snapshot:
                from_snapshot = part.snapshot
            if part.type == "step-finish" and part.snapshot:
                to_snapshot = part.snapshot
    if from_snapshot and to_snapshot:
        return await snapshot_diff_full(from_snapshot, to_snapshot)
    return []
```

#### 触发时机

- 主循环 step === 1 时调用 `summarize(session_id, last_user.id)`
- processor 每个 `finish-step` 事件后调用 `summarize(session_id, parent_id)`

---

### Processor 流式处理与重试

对应 `session/processor.ts`，消费 LLM 流式响应。

#### 流事件处理

| 流事件 | 处理 |
|:---|:---|
| `start` | 设置 session 状态为 `busy` |
| `reasoning-start/delta/end` | 创建/追加/完成 `ReasoningPart` |
| `text-start/delta/end` | 创建/追加/完成 `TextPart` |
| `tool-input-start` | 创建 `ToolPart`（status=pending） |
| `tool-call` | `ToolPart` 状态改为 running；**Doom Loop 检测** |
| `tool-result` | `ToolPart` 状态改为 completed |
| `tool-error` | `ToolPart` 状态改为 error；若是 `PermissionRejected` 则 `blocked=True` |
| `start-step` | `Snapshot.track()` → 创建 `StepStartPart` |
| `finish-step` | 记录 token/cost → 创建 `StepFinishPart` → **检测溢出** → 触发 summarize |
| `error` | 抛出异常，进入重试逻辑 |

#### Doom Loop 检测

```python
DOOM_LOOP_THRESHOLD = 3

# 取最近 3 个 tool parts
last_three = parts[-DOOM_LOOP_THRESHOLD:]
if (len(last_three) == DOOM_LOOP_THRESHOLD
        and all(p.type == "tool" for p in last_three)
        and all(p.tool == tool_name for p in last_three)
        and all(p.state.status != "pending" for p in last_three)
        and all(json.dumps(p.state.input, sort_keys=True) == json.dumps(input, sort_keys=True)
                for p in last_three)):
    # 弹出权限确认
    await permission_ask(permission="doom_loop", patterns=[tool_name])
```

#### 重试逻辑

```python
RETRY_INITIAL_DELAY = 2_000      # 2 秒
RETRY_BACKOFF_FACTOR = 2
RETRY_MAX_DELAY_NO_HEADERS = 30_000  # 30 秒

def retry_delay(attempt: int, error: APIError | None = None) -> int:
    """计算重试延迟（毫秒）"""
    if error and error.response_headers:
        headers = error.response_headers
        # 1. 优先使用 retry-after-ms
        if "retry-after-ms" in headers:
            return float(headers["retry-after-ms"])
        # 2. retry-after（秒或 HTTP date）
        if "retry-after" in headers:
            seconds = try_parse_float(headers["retry-after"])
            if seconds is not None:
                return int(seconds * 1000)
            # 尝试解析为 HTTP date
            parsed = parse_http_date(headers["retry-after"])
            if parsed:
                return max(0, int((parsed - datetime.now()).total_seconds() * 1000))
        # 有 headers 但没有 retry-after，用指数退避（无上限）
        return RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1))

    # 无 headers，指数退避，cap 30s
    return min(
        RETRY_INITIAL_DELAY * (RETRY_BACKOFF_FACTOR ** (attempt - 1)),
        RETRY_MAX_DELAY_NO_HEADERS,
    )

def is_retryable(error) -> str | None:
    """判断错误是否可重试，返回提示消息或 None"""
    if isinstance(error, ContextOverflowError):
        return None  # 不重试
    if isinstance(error, APIError):
        if not error.is_retryable:
            return None
        return "Provider is overloaded" if "Overloaded" in error.message else error.message
    # 尝试解析 JSON 格式的错误
    # too_many_requests / rate_limit / exhausted / unavailable → 可重试
    return None
```

#### 上下文溢出错误检测

```python
OVERFLOW_PATTERNS = [
    r"prompt is too long",                     # Anthropic
    r"input is too long for requested model",  # Amazon Bedrock
    r"exceeds the context window",             # OpenAI
    r"input token count.*exceeds the maximum", # Google Gemini
    r"maximum prompt length is \d+",           # xAI Grok
    r"reduce the length of the messages",      # Groq
    r"maximum context length is \d+ tokens",   # OpenRouter, DeepSeek
    r"exceeds the limit of \d+",               # GitHub Copilot
    r"exceeds the available context size",      # llama.cpp
    r"greater than the context length",         # LM Studio
    r"context window exceeds limit",            # MiniMax
    r"exceeded model token limit",              # Kimi / Moonshot
    r"context[_ ]length[_ ]exceeded",           # Generic fallback
]

def is_context_overflow(message: str) -> bool:
    return any(re.search(p, message, re.IGNORECASE) for p in OVERFLOW_PATTERNS)
```

检测到后创建 `ContextOverflowError`，**不重试**。

---

### 关键常量汇总

| 常量 | 值 | 用途 | 所在模块 |
|:---|:---|:---|:---|
| `COMPACTION_BUFFER` | 20,000 tokens | 溢出检测的默认预留 | `session/compaction.py` |
| `PRUNE_MINIMUM` | 20,000 tokens | 低于此阈值不执行 pruning | `session/compaction.py` |
| `PRUNE_PROTECT` | 40,000 tokens | 保护最近这么多 token 的工具输出 | `session/compaction.py` |
| `PRUNE_PROTECTED_TOOLS` | `["skill"]` | 永不裁剪的工具 | `session/compaction.py` |
| `MAX_LINES` | 2,000 | 工具输出最大行数 | `tool/truncation.py` |
| `MAX_BYTES` | 50KB | 工具输出最大字节 | `tool/truncation.py` |
| `OUTPUT_TOKEN_MAX` | 32,000 | 默认最大输出 token | `agent/llm.py` |
| `CHARS_PER_TOKEN` | 4 | Token 估算因子 | `util/token.py` |
| `DOOM_LOOP_THRESHOLD` | 3 | 连续相同调用触发 doom loop | `session/processor.py` |
| `RETRY_INITIAL_DELAY` | 2,000ms | 重试初始延迟 | `agent/retry.py` |
| `RETRY_BACKOFF_FACTOR` | 2 | 退避倍数 | `agent/retry.py` |
| `RETRY_MAX_DELAY_NO_HEADERS` | 30,000ms | 无 header 时最大延迟 | `agent/retry.py` |
| Truncate cleanup | 7 天 / 每小时 | 截断文件清理周期 | `tool/truncation.py` |

---

### 完整数据流时序图

```
User 输入 "Fix bug in foo.ts"
│
▼ create_user_message()
  → Storage: message/{session_id}/{msg_id}.json  (role=user)
  → Storage: part/{msg_id}/{part_id}.json        (type=text, text="Fix bug...")

▼ loop() step=1
  │
  ├─ filter_compacted()
  │    → 从新到旧读 message/*.json
  │    → 遇到 compaction 边界则截断
  │    → 返回 [compaction_summary, ..., current_msg]
  │
  ├─ is_overflow(last_finished.tokens, model)?
  │    → tokens.total >= model.input_limit - 20000?
  │    → NO → 继续
  │
  ├─ insert_reminders()
  │    → if agent=plan: 注入 plan mode 指示
  │    → if 从 plan 切到 build: 注入 "执行计划" 指示
  │
  ├─ resolve_tools(agent, model)
  │    → 内置工具 + MCP 工具
  │    → 过滤被 permission deny 的工具
  │
  ├─ 系统提示组装
  │    → [environment] + [instructions] + [agent.prompt]
  │
  ├─ to_model_messages(msgs, model)
  │    → compaction part → "What did we do so far?"
  │    → compacted tool → "[Old tool result content cleared]"
  │    → error assistant → 跳过
  │
  ├─ apply_caching() [仅 Anthropic]
  │    → 前2系统消息 + 后2对话消息 标记 ephemeral cache
  │
  ├─ llm_stream()
  │    ├─ stream_text(system, messages, tools, model)
  │    │
  │    ├─ 流事件处理:
  │    │   start-step → Snapshot.track() → StepStartPart
  │    │   text-delta → TextPart 追加
  │    │   tool-call  → ToolPart(running) + doom loop 检查
  │    │   tool-result → ToolPart(completed)
  │    │   finish-step → StepFinishPart + token/cost 记录
  │    │                 → is_overflow? → needs_compaction = True
  │    │
  │    └─ 错误处理:
  │        → retryable? → 指数退避重试
  │        → ContextOverflow? → 不重试
  │        → 其他 → 记录 error 并 stop
  │
  ├─ result = "continue" / "stop" / "compact"
  │    → compact → compaction_create() → 下轮执行
  │    → continue → 下轮循环
  │    → stop → 退出循环
  │
  ▼ 循环结束后
  │
  ├─ compaction_prune()
  │    → 扫描旧工具输出
  │    → 保护最近 40K token
  │    → 超出部分 mark time.compacted
  │
  └─ summarize()
       → compute_diff(snapshots) → session.summary
       → title_agent → session.title
```

### 上下文管理分层策略总结

整个系统采用**三层渐进式上下文管理**：

| 层级 | 机制 | 触发时机 | 效果 |
|:---|:---|:---|:---|
| **L1：即时截断** | `truncation.py` — 2000行/50KB | 每次工具执行完毕 | 防止单次工具输出爆炸 |
| **L2：延迟裁剪** | `prune()` — 保护最近 40K token | 主循环结束后 | 渐进清除旧工具输出，`"[Old tool result content cleared]"` |
| **L3：全量压缩** | `compaction` — LLM 生成结构化摘要 | token 数逼近上限时 | 全部旧消息被摘要替代，只保留摘要+新消息 |

配合 **instruction files** 提供跨会话的长期记忆（项目级 AGENTS.md），以及 **git snapshots** 提供文件级别的状态回溯能力。

---

## 6. 权限系统 (`permission/permission.py`)

**Last-match-wins** 规则求值，与 OpenCode 一致：

```python
def evaluate(permission: str, pattern: str, *rulesets: list[Rule]) -> Rule:
    merged = [rule for rs in rulesets for rule in rs]
    match = None
    for rule in merged:
        if wildcard_match(permission, rule.permission) and wildcard_match(pattern, rule.pattern):
            match = rule
    return match or Rule(permission=permission, pattern="*", action="ask")
```

HTTP 模式下的 "ask" 流程：
1. Agent 触发 `permission.ask()` → 发布 SSE 事件 `permission.asked`
2. Agent 阻塞等待（`asyncio.Event.wait()`）
3. 客户端通过 `POST /permission/{id}` 回复 `once`/`always`/`reject`
4. 解除阻塞，Agent 继续或抛出 `PermissionDeniedError`

---

## 7. Skill 系统 (`skill/skill.py`)

SKILL.md 格式（YAML frontmatter + Markdown body）：
```markdown
---
name: deploy
description: 项目部署流程
---
# 部署步骤
1. 运行测试...
2. 构建镜像...
```

发现顺序（后覆盖前）：
1. `~/.openagent/skills/**/SKILL.md` — 全局
2. `.openagent/skills/**/SKILL.md` — 项目级
3. `.claude/skills/`, `.agents/skills/` — 兼容 Claude Code
4. `config.skills.paths` — 配置指定路径
5. `config.skills.urls` — 远程索引（拉取 `index.json`）

SkillTool 动态生成描述列出所有可用 Skill，LLM 调用时注入 Skill 内容到上下文。

---

## 8. MCP 集成 (`mcp/client.py`)

使用 Python `mcp` SDK：
- **Local**：`stdio_client()` 启动子进程，通过 stdin/stdout 通信
- **Remote**：`sse_client()` 连接 HTTP/SSE 端点
- 工具名前缀：`{sanitized_server_name}_{sanitized_tool_name}`
- 连接生命周期：启动时并行连接所有配置的服务器，支持动态 connect/disconnect

---

## 9. HTTP API 端点

```
# Session
POST   /session                         # 创建 Session
GET    /session                         # 列出 Session
GET    /session/{id}                    # 获取 Session
DELETE /session/{id}                    # 删除 Session
PATCH  /session/{id}                    # 更新 Session（标题等）

# 消息与 Agent 控制
POST   /session/{id}/message            # 发送消息（触发 Agent 循环，阻塞到完成）
POST   /session/{id}/prompt_async       # 异步发送消息（立即返回 204）
GET    /session/{id}/message            # 获取消息列表
POST   /session/{id}/abort             # 取消运行中的 Session
POST   /session/{id}/summarize         # 手动触发上下文压缩
POST   /session/{id}/revert/{msg_id}   # 撤销到指定消息（回滚文件修改）
POST   /session/{id}/unrevert          # 恢复被撤销的修改
POST   /session/{id}/command           # 执行命令模板（斜杠命令）
GET    /session/{id}/todo              # 获取 Todo 列表
GET    /session/{id}/diff              # 获取文件变更 diff

# 实时事件
GET    /event                           # SSE 事件流

# 权限 & 问答
POST   /permission/{id}                # 回复权限请求（once/always/reject）
POST   /question/{id}                  # 回复 LLM 提问

# 元数据
GET    /config                          # 获取配置
GET    /agent                           # 列出 Agent
GET    /skill                           # 列出 Skill
GET    /command                         # 列出可用命令模板
GET    /mcp                             # MCP 服务器状态
POST   /mcp/{name}/connect             # 连接 MCP 服务器
POST   /mcp/{name}/disconnect          # 断开 MCP 服务器
```

---

## 10. 配置文件格式 (`openagent.json`)

```jsonc
{
  "model": "anthropic/claude-sonnet-4-20250514",
  "provider": {
    "anthropic": { "options": { "apiKey": "{env:ANTHROPIC_API_KEY}" } }
  },
  "agent": {
    "build": { "temperature": 0.0, "prompt": "You are a helpful agent..." },
    "explore": { "model": "anthropic/claude-haiku-3-20250714", "mode": "subagent" }
  },
  "permission": {
    "bash": { "git *": "allow", "*": "ask" },
    "edit": "ask",
    "read": "allow"
  },
  "mcp": {
    "filesystem": { "type": "local", "command": ["npx", "-y", "@mcp/server-fs", "/tmp"] },
    "remote": { "type": "remote", "url": "https://mcp.example.com/sse" }
  },
  "skills": {
    "paths": ["./custom-skills"],
    "urls": ["https://example.com/.well-known/skills/"]
  },
  "server": { "port": 4096, "hostname": "127.0.0.1" },
  "sandbox": {
    "openbox_url": "http://localhost:8080",
    "image": "openbox-sandbox:latest",
    "auto_destroy": true,
    "resources": { "memory": "512m", "cpu": 0.5 }
  }
}
```

---

## 依赖

```toml
[project]
name = "openagent"
requires-python = ">=3.11"
dependencies = [
    # 核心 Agent 引擎
    "pydantic-ai>=0.1",           # 工具执行循环 + 类型安全（替代 Vercel AI SDK）
    "litellm>=1.50",              # 100+ LLM 供应商统一接入
    "pydantic>=2.0",              # 数据校验

    # HTTP API
    "fastapi>=0.115",             # HTTP 框架
    "uvicorn[standard]>=0.30",    # ASGI 服务器
    "sse-starlette>=2.0",         # SSE 支持

    # 异步 IO
    "aiofiles>=24.0",             # 异步文件 IO
    "httpx>=0.27",                # 异步 HTTP 客户端

    # 扩展
    "mcp>=1.0",                   # MCP Python SDK
    "python-frontmatter>=1.1",    # Markdown frontmatter 解析
    "pyyaml>=6.0",                # YAML
    "python-ulid>=3.0",           # ULID ID 生成
]
```

---

## 实现顺序

### Phase 0：沙箱环境准备
0. 扩展 OpenBox Action Server — 新增 `/write_file`、`/read_file`、`/glob`、`/grep`、`/execute_stream` 端点
   - 文件：`container/action_server.py`

### Phase 1：基础设施
1. `util/` — ID 生成、日志、通配符匹配
2. `storage/` — 文件系统 JSON 存储
3. `bus/` — 事件总线
4. `config/` — 配置加载与校验
5. `sandbox/` — 沙箱管理器 + 客户端 + Session 映射
6. `project/` — 项目发现（git root → 项目 ID）+ 运行时上下文

### Phase 2：核心模型
7. `session/message.py` — Message/Part Pydantic 模型
8. `session/session.py` — Session CRUD
9. `session/todo.py` — 会话级 Todo 存储
10. `permission/permission.py` — 权限规则求值
11. `question/question.py` — 用户问答管理

### Phase 3：工具系统
12. `tool/tool.py` — 工具基类 + 工厂
13. `tool/truncation.py` — 输出截断
14. `tool/invalid.py` — 错误恢复工具
15. `tool/registry.py` — 工具注册表
16. `tool/bash.py` — Shell 执行（第一个可测试的工具）
17. `tool/read.py`, `write.py`, `edit.py` — 文件操作工具
18. `tool/apply_patch.py` — 结构化补丁工具
19. `tool/glob_tool.py`, `grep.py` — 搜索工具
20. `tool/question.py` — LLM 提问工具
21. `tool/todo.py` — TodoWrite/TodoRead 工具
22. `tool/batch.py` — 并行工具调用

### Phase 4：Agent 循环（核心）
23. `agent/retry.py` — 重试逻辑（指数退避）
24. `agent/hooks.py` — 工具执行钩子（权限、doom loop、SSE 事件推送）
25. `agent/llm.py` — Pydantic AI + LiteLLM 封装（单轮工具循环由框架处理）
26. `agent/loop.py` — 外层循环（多轮编排、compaction 触发、max steps）
27. `agent/agent.py` — 多 Agent 定义（build/plan/explore/general/compaction/title）
28. `agent/compaction.py` — 上下文压缩 + 旧工具输出裁剪（pruning）
29. `snapshot/snapshot.py` — 文件快照（git write-tree）
30. `session/revert.py` — 按消息粒度撤销修改

### Phase 5：HTTP API
31. `server/app.py` — FastAPI 应用
32. `server/routes/event.py` — SSE 事件流
33. `server/routes/session.py` — Session + 消息 + revert + command 接口
34. `server/routes/permission.py` — 权限应答接口
35. `server/routes/question.py` — LLM 提问应答接口
36. 其余路由（config, agent, skill, mcp, todo, diff）

### Phase 6：扩展机制
37. `skill/` — Skill 发现与加载
38. `tool/skill.py` — Skill 工具
39. `tool/plan.py` — Plan 模式切换
40. `tool/task.py` — 子 Agent 工具
41. `tool/web_fetch.py`, `web_search.py` — Web 工具
42. `mcp/client.py` — MCP 集成
43. `command/command.py` — 命令模板系统
44. 自定义工具加载（`.openagent/tools/*.py`）

### Phase 7：收尾
45. `__main__.py` — 启动入口
46. 集成测试
47. OpenAPI 文档

---

## 暂不实现（后续迭代）

以下功能对 v1 不是必需的，可在后续版本中添加：

| 功能 | 原因 |
|------|------|
| LSP 集成 | 工程量大（需对接多语言 LSP 服务器），编码场景专用 |
| 代码自动格式化 | 依赖 LSP / 外部 formatter，编码场景专用 |
| PTY 伪终端 | 需要 WebSocket，交互式终端是 UI 功能 |
| Git Worktree | 高级并行功能，v1 用单目录即可 |
| ACP 协议 | 编辑器集成协议，HTTP API 已够用 |
| Session 分享 | 社区功能，非核心 |
| 文件监听 | 可用轮询替代 |
| Plugin Auth Hooks | v1 使用 LiteLLM 自带的 API Key 认证即可 |

---

## 验证方式

1. **单元测试**：每个模块独立测试（pytest + pytest-asyncio）
2. **工具测试**：用真实文件系统测试 bash/read/write/edit/glob/grep
3. **Agent 循环测试**：mock LiteLLM，验证循环控制流（stop/continue/compact）
4. **API 测试**：用 FastAPI TestClient 测试完整 HTTP 流程
5. **端到端测试**：启动服务 → 创建 Session → 发送消息 → 通过 SSE 接收事件 → 验证工具被调用并返回结果
6. **MCP 测试**：启动一个简单的 MCP stdio 服务器，验证工具发现和调用
7. **Skill 测试**：创建测试 SKILL.md，验证发现、加载和注入
