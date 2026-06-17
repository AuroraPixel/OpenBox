# OpenBox Backend API Interfaces

前端所需的全部后端接口定义。

**Base URL**: 由 `VITE_API_URL` 环境变量配置，默认为当前域名。

**通用约定**:
- Content-Type: `application/json`
- 错误响应: `{ "detail": "error message" }`
- 时间格式: ISO 8601 (`2024-01-01T00:00:00Z`)

---

## 目录

1. [Container 容器管理](#1-container-容器管理) (9 个)
2. [Session 会话管理](#2-session-会话管理) (5 个)
3. [Message 消息](#3-message-消息) (4 个)
4. [Compaction 上下文压缩](#4-compaction-上下文压缩) (1 个)
5. [Revert 回滚](#5-revert-回滚) (2 个)
6. [Command 命令执行](#6-command-命令执行) (1 个)
7. [Todo 任务列表](#7-todo-任务列表) (1 个)
8. [Diff 代码变更](#8-diff-代码变更) (1 个)
9. [Permission 权限确认](#9-permission-权限确认) (1 个)
10. [Question 交互提问](#10-question-交互提问) (1 个)
11. [Config 配置与元数据](#11-config-配置与元数据) (7 个)
12. [SSE 实时事件流](#12-sse-实时事件流) (1 个 + 17 种事件)
13. [WebSocket 终端](#13-websocket-终端) (1 个)
14. [Type 类型定义汇总](#14-type-类型定义汇总)

**接口总计**: 33 个 HTTP + 1 个 SSE + 1 个 WebSocket = **35 个接口**

---

## 1. Container 容器管理

### 1.1 创建容器

```
POST /api/containers
```

**Request Body**:
```typescript
{
  name: string           // 容器名称
  image?: string         // Docker 镜像，可选
}
```

**Response** `200`:
```typescript
ContainerInfo
```

---

### 1.2 容器列表

```
GET /api/containers
```

**Response** `200`:
```typescript
{
  containers: ContainerInfo[]
  total: number
}
```

---

### 1.3 获取容器详情

```
GET /api/containers/:id
```

**Response** `200`:
```typescript
ContainerInfo
```

---

### 1.4 删除容器

```
DELETE /api/containers/:id
```

**Response** `200`: `void`

---

### 1.5 停止容器

```
POST /api/containers/:id/stop
```

**Response** `200`: `void`

---

### 1.6 启动容器

```
POST /api/containers/:id/start
```

**Response** `200`: `void`

---

### 1.7 获取系统信息

```
GET /api/containers/:containerId/files/system_info
```

**Response** `200`:
```typescript
{
  cpu: { percent: number; count: number }
  memory: { total: number; used: number; percent: number }
  disk: { total: number; used: number; free: number; percent: number }
}
```

---

### 1.8 列出文件

```
POST /api/containers/:containerId/files/list
```

**Request Body**:
```typescript
{
  path: string           // 目录路径，如 "/workspace"
}
```

**Response** `200`:
```typescript
{
  files: Array<{
    name: string
    is_dir: boolean
    size: number | null
    modified: string | null   // ISO 8601
  }>
}
```

---

### 1.9 终端 WebSocket URL

```
WS /ws/terminal/:containerId
```

> 由前端拼接生成，不是 HTTP 接口。详见 [WebSocket 终端](#13-websocket-终端)。

---

## 2. Session 会话管理

### 2.1 创建会话

```
POST /api/agent/session
```

**Request Body**: 无

**Response** `200`:
```typescript
Session
```

---

### 2.2 会话列表

```
GET /api/agent/session
```

**Response** `200`:
```typescript
Session[]
```

---

### 2.3 获取会话详情

```
GET /api/agent/session/:id
```

**Response** `200`:
```typescript
Session
```

---

### 2.4 删除会话

```
DELETE /api/agent/session/:id
```

**Response** `200`: `void`

---

### 2.5 更新会话

```
PATCH /api/agent/session/:id
```

**Request Body**:
```typescript
Partial<Session>         // 可更新 title, agent, model 等字段
```

**Response** `200`:
```typescript
Session
```

---

## 3. Message 消息

### 3.1 获取消息列表

```
GET /api/agent/session/:sessionId/message
```

**Response** `200`:
```typescript
MessageWithParts[]
```

---

### 3.2 发送消息（同步）

```
POST /api/agent/session/:sessionId/message
```

**Request Body**:
```typescript
{
  text: string
}
```

**Response** `200`:
```typescript
MessageWithParts
```

---

### 3.3 发送消息（异步 + SSE 流式响应）

```
POST /api/agent/session/:sessionId/prompt_async
```

> 发送后立即返回，后续通过 SSE 推送流式响应。

**Request Body**:
```typescript
{
  text: string
  agent?: string         // 指定 agent，如 "build", "explore"
  model?: string         // 指定模型，如 "anthropic/claude-sonnet-4"
  variant?: string       // 模型变体
}
```

**Response** `200`:
```typescript
{ ok: boolean }
```

---

### 3.4 中断会话

```
POST /api/agent/session/:sessionId/abort
```

**Response** `200`: `void`

---

## 4. Compaction 上下文压缩

### 4.1 触发压缩

```
POST /api/agent/session/:sessionId/summarize
```

> 触发上下文压缩。后端通过 SSE 推送 `session.compaction.start` 和 `session.compaction.complete` 事件。

**Response** `200`: `void`

---

## 5. Revert 回滚

### 5.1 回滚到指定消息

```
POST /api/agent/session/:sessionId/revert/:messageId
```

> 回滚会话状态到指定消息（含文件变更回退）。

**Response** `200`: `void`

---

### 5.2 撤销回滚

```
POST /api/agent/session/:sessionId/unrevert
```

**Response** `200`: `void`

---

## 6. Command 命令执行

### 6.1 执行斜杠命令

```
POST /api/agent/session/:sessionId/command
```

**Request Body**:
```typescript
{
  command: string        // 命令名（不含 /），如 "commit", "review"
  arguments?: string     // 命令参数
}
```

**Response** `200`: `void`

---

## 7. Todo 任务列表

### 7.1 获取 Todo

```
GET /api/agent/session/:sessionId/todo
```

**Response** `200`:
```typescript
{
  items: TodoItem[]
}
```

---

## 8. Diff 代码变更

### 8.1 获取会话 Diff

```
GET /api/agent/session/:sessionId/diff
```

**Response** `200`:
```typescript
DiffEntry[]
```

---

## 9. Permission 权限确认

### 9.1 回复权限请求

```
POST /api/agent/permission/:id
```

> 当 Agent 请求执行危险操作时，前端通过 SSE 收到 `permission.asked` 事件后，调用此接口回复。

**Request Body**:
```typescript
{
  action: "once" | "always" | "reject"
}
```

**Response** `200`: `void`

---

## 10. Question 交互提问

### 10.1 回复提问

```
POST /api/agent/question/:id
```

> 当 Agent 向用户提问时，前端通过 SSE 收到 `question.asked` 事件后，调用此接口回复。

**Request Body**:
```typescript
{
  answers: Record<string, string>   // key: 问题 ID, value: 选择的答案
}
```

**Response** `200`: `void`

---

## 11. Config 配置与元数据

### 11.1 获取应用配置

```
GET /api/agent/config
```

**Response** `200`:
```typescript
{
  models: ModelInfo[]
  default_model: string       // 如 "anthropic/claude-sonnet-4"
  default_agent: string       // 如 "build"
}
```

---

### 11.2 Agent 列表

```
GET /api/agent/agent
```

**Response** `200`:
```typescript
AgentConfig[]
```

---

### 11.3 Skill 列表

```
GET /api/agent/skill
```

**Response** `200`:
```typescript
SkillInfo[]
```

---

### 11.4 Command 列表

```
GET /api/agent/command
```

**Response** `200`:
```typescript
CommandInfo[]
```

---

### 11.5 MCP 服务器状态

```
GET /api/agent/mcp
```

**Response** `200`:
```typescript
McpServer[]
```

---

### 11.6 连接 MCP 服务器

```
POST /api/agent/mcp/:name/connect
```

**Response** `200`: `void`

---

### 11.7 断开 MCP 服务器

```
POST /api/agent/mcp/:name/disconnect
```

**Response** `200`: `void`

---

## 12. SSE 实时事件流

### 连接端点

```
GET /api/agent/event
```

> 使用浏览器原生 `EventSource` API 连接。每条消息格式为 `data: JSON\n\n`。

### 消息格式

```typescript
{
  type: string           // 事件类型
  data: object           // 事件数据
}
```

### 12.1 事件类型清单

#### Session 事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `session.status` | `{ sessionId: string; status: SessionStatus }` | 会话状态变更 |
| `session.title` | `{ sessionId: string; title: string }` | 会话标题更新（Agent 自动生成） |
| `session.error` | `{ sessionId: string; error: { message: string } }` | 会话错误 |
| `session.diff` | `{ sessionId: string }` | 代码变更通知（触发前端 refetch diff） |
| `session.compaction.start` | `{ sessionId: string }` | 开始上下文压缩 |
| `session.compaction.complete` | `{ sessionId: string }` | 压缩完成 |

#### Message 事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `message.created` | `{ sessionId: string; message: MessageWithParts }` | 新消息（user 或 assistant） |
| `message.updated` | `{ sessionId: string; message: MessageWithParts }` | 消息更新（完整替换） |
| `message.text_delta` | `{ sessionId: string; messageId: string; partId: string; text: string }` | 文本增量（流式打字效果） |

#### Part 事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `part.created` | `{ sessionId: string; messageId: string; part: MessagePart }` | 新 Part 添加到消息 |
| `part.updated` | `{ sessionId: string; messageId: string; part: MessagePart }` | Part 内容更新 |
| `part.delta` | `{ sessionId: string; messageId: string; partId: string; delta: string }` | Part 文本增量（reasoning 打字效果） |

#### Tool 事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `tool.running` | `{ sessionId: string; partId: string; tool: string; input: Record<string, unknown> }` | 工具开始执行 |
| `tool.completed` | `{ sessionId: string; partId: string; output: string; title?: string }` | 工具执行完成 |
| `tool.error` | `{ sessionId: string; partId: string; error: string }` | 工具执行出错 |

#### 交互事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `permission.asked` | `PermissionRequest` | Agent 请求权限确认 |
| `question.asked` | `QuestionRequest` | Agent 向用户提问 |

#### 其他事件

| 事件类型 | data 结构 | 说明 |
|---------|----------|------|
| `todo.updated` | `{ sessionId: string }` | Todo 列表变更（触发 refetch） |

---

## 13. WebSocket 终端

### 连接端点

```
WS /ws/terminal/:containerId
```

> HTTP 协议部分自动替换为 `ws://` 或 `wss://`。

### 二进制帧协议

| 前缀字节 | 含义 | 数据 |
|---------|------|------|
| `0x00` | 数据帧 | 终端输入/输出数据 |
| `0x01` | 窗口调整 | 行列大小（JSON 或二进制编码） |

### JSON 消息格式

```typescript
{
  type: "input" | "output" | "error" | "heartbeat"
  data?: string
  exit_code?: number
}
```

---

## 14. Type 类型定义汇总

### ContainerInfo

```typescript
interface ContainerInfo {
  id: string
  name: string
  status: "creating" | "running" | "stopped" | "error"
  image: string
  created_at: string
  port: number | null
  api_key: string | null
}
```

### Session

```typescript
interface Session {
  id: string
  title: string
  agent: string                   // 使用的 agent 名称
  model: string                   // 使用的模型 ID
  status: "idle" | "busy" | "retry" | "error" | "compacting"
  created_at: string
  updated_at: string
  additions?: number              // 新增行数
  deletions?: number              // 删除行数
  files_changed?: number          // 变更文件数
  token_usage?: TokenUsage
}
```

### TokenUsage

```typescript
interface TokenUsage {
  input: number
  output: number
  cache: number
  total: number
  limit: number
  cost: number                    // 单位: USD
}
```

### MessageWithParts

```typescript
interface MessageWithParts {
  id: string
  session_id: string
  role: "user" | "assistant" | "system"
  parts: MessagePart[]
  created_at: string
  agent?: string
  model?: string
}
```

### MessagePart（联合类型）

```typescript
type MessagePart =
  | TextPart           // { type: "text", id, text }
  | ReasoningPart      // { type: "reasoning", id, text }
  | ToolPartData       // { type: "tool", id, tool, status, input?, output?, error?, title?, duration? }
  | StepStartPart      // { type: "step-start", id, step }
  | StepFinishPart     // { type: "step-finish", id, step, input_tokens, output_tokens, cost, duration }
  | CompactionPart     // { type: "compaction", id, summary? }
  | SubtaskPart        // { type: "subtask", id, agent, description, status, output? }
  | PatchPart          // { type: "patch", id, files: PatchFile[] }
  | FilePart           // { type: "file", id, path, mime_type?, url? }
  | AgentSwitchPart    // { type: "agent", id, agent }
  | RetryPart          // { type: "retry", id, attempt, reason? }
```

### PatchFile

```typescript
interface PatchFile {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
}
```

### DiffEntry

```typescript
interface DiffEntry {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
  hunks?: DiffHunk[]
}

interface DiffHunk {
  old_start: number
  old_count: number
  new_start: number
  new_count: number
  lines: DiffLine[]
}

interface DiffLine {
  type: "add" | "del" | "context"
  content: string
  old_line?: number
  new_line?: number
}
```

### TodoItem / TodoList

```typescript
interface TodoItem {
  id: string
  subject: string
  description?: string
  status: "pending" | "in_progress" | "completed"
  active_form?: string
}

interface TodoList {
  items: TodoItem[]
}
```

### AgentConfig

```typescript
interface AgentConfig {
  name: string
  description: string
  model: string
  temperature: number
  tools: string[]
  system_prompt?: string
}
```

### ModelInfo

```typescript
interface ModelInfo {
  id: string
  name: string
  provider: string
  max_tokens: number
  variants?: string[]
}
```

### SkillInfo

```typescript
interface SkillInfo {
  name: string
  description: string
  source: "global" | "project" | "remote"
  content?: string
}
```

### McpServer / McpTool

```typescript
interface McpServer {
  name: string
  type: "stdio" | "remote"
  status: "connected" | "disconnected" | "error"
  tools: McpTool[]
  error?: string
}

interface McpTool {
  name: string
  description: string
}
```

### CommandInfo

```typescript
interface CommandInfo {
  name: string
  description: string
  arguments?: string
}
```

### AppConfig

```typescript
interface AppConfig {
  models: ModelInfo[]
  default_model: string
  default_agent: string
}
```

### PermissionRequest / PermissionReply

```typescript
interface PermissionRequest {
  id: string
  session_id: string
  tool: string
  input: Record<string, unknown>
  patterns?: string[]
  metadata?: Record<string, unknown>
  is_doom_loop?: boolean
  created_at: string
}

type PermissionAction = "once" | "always" | "reject"

interface PermissionReply {
  id: string
  action: PermissionAction
}
```

### QuestionRequest / QuestionReply

```typescript
interface QuestionRequest {
  id: string
  session_id: string
  questions: Question[]
  created_at: string
}

interface Question {
  question: string
  header?: string
  options: QuestionOption[]
  multi_select: boolean
}

interface QuestionOption {
  label: string
  description?: string
}

interface QuestionReply {
  id: string
  answers: Record<string, string>
}
```
