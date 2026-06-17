# OpenAgent 前端设计文档

基于 OpenBox 现有前端（React 19 + Vite + Tailwind）重新设计，从纯沙箱管理工具升级为完整的 AI Agent 交互平台。

**现有前端能力**：沙箱容器 CRUD、xterm.js 终端、WebSocket PTY —— 全部保留并增强。

**新增核心能力**：AI 对话界面、Agent 工具执行可视化、Session 管理、权限交互、实时事件流。

---

## 目录

1. [技术选型](#技术选型)
2. [整体布局](#整体布局)
3. [路由结构](#路由结构)
4. [状态管理](#状态管理)
5. [通信层](#通信层)
6. [功能模块详解](#功能模块详解)
   - [M1: Session 管理](#m1-session-管理)
   - [M2: AI 对话界面](#m2-ai-对话界面)
   - [M3: 消息渲染系统](#m3-消息渲染系统)
   - [M4: 工具执行可视化](#m4-工具执行可视化)
   - [M5: 权限交互](#m5-权限交互)
   - [M6: 用户问答交互](#m6-用户问答交互)
   - [M7: Todo 任务面板](#m7-todo-任务面板)
   - [M8: Plan 模式](#m8-plan-模式)
   - [M9: 上下文管理可视化](#m9-上下文管理可视化)
   - [M10: 沙箱管理（增强）](#m10-沙箱管理增强)
   - [M11: 终端（增强）](#m11-终端增强)
   - [M12: 文件浏览器](#m12-文件浏览器)
   - [M13: Diff 查看器](#m13-diff-查看器)
   - [M14: Agent 与模型配置](#m14-agent-与模型配置)
   - [M15: Skill 管理](#m15-skill-管理)
   - [M16: MCP 服务器管理](#m16-mcp-服务器管理)
   - [M17: 命令面板](#m17-命令面板)
   - [M18: 全局通知与状态栏](#m18-全局通知与状态栏)
7. [SSE 事件驱动架构](#sse-事件驱动架构)
8. [响应式设计](#响应式设计)
9. [主题系统](#主题系统)
10. [实现优先级](#实现优先级)

---

## 技术选型

| 技术 | 选择 | 理由 |
|------|------|------|
| 框架 | React 19 | 现有基础，生态成熟 |
| 构建 | Vite 6 | 现有基础，快速 HMR |
| 样式 | Tailwind CSS 4 | 现有基础 |
| 路由 | **TanStack Router** | 类型安全路由，支持 loader/搜索参数 |
| 状态管理 | **Zustand** | 轻量，TS 友好，支持中间件（devtools、persist） |
| 异步数据 | **TanStack Query** | 自动缓存/重验证/轮询，替代手写 useEffect+fetch |
| Markdown | **react-markdown** + **remark-gfm** + **rehype-highlight** | 渲染 LLM 输出的 Markdown/代码块 |
| Diff | **react-diff-viewer-continued** 或 **diff2html** | 文件变更 diff 渲染 |
| 代码编辑 | **@monaco-editor/react** (可选) | 文件编辑器，后期加入 |
| 终端 | @xterm/xterm（保留） | 现有基础 |
| 图标 | lucide-react（保留） | 现有基础 |
| 表单 | **react-hook-form** + **zod** | 类型安全表单校验 |
| 动画 | **framer-motion** (可选) | 消息出现/工具展开动画 |
| 组件库 | 自建（基于 Tailwind） | 保持轻量，不依赖 shadcn/radix 整套 |

---

## 整体布局

```
┌──────────────────────────────────────────────────────────────────────┐
│  StatusBar（全局状态栏）                                              │
│  [Session 标题] [Agent: build ▾] [Model: claude-sonnet ▾] [Token ●] │
├──────────┬───────────────────────────────────────────────┬───────────┤
│          │                                               │           │
│ Sidebar  │            Main Content Area                  │  Right    │
│          │                                               │  Panel    │
│ ┌──────┐ │  ┌─────────────────────────────────────────┐  │ (可折叠)  │
│ │Session│ │  │                                         │  │           │
│ │ List  │ │  │   Chat / Terminal / Files / Diff        │  │ ┌───────┐│
│ │      │ │  │   （根据路由切换）                        │  │ │ Todo  ││
│ │ ━━━━ │ │  │                                         │  │ │ List  ││
│ │      │ │  │                                         │  │ ├───────┤│
│ │Sandbox│ │  │                                         │  │ │Context││
│ │ List  │ │  │                                         │  │ │ Info  ││
│ │      │ │  │                                         │  │ ├───────┤│
│ │ ━━━━ │ │  │                                         │  │ │ File  ││
│ │Quick │ │  │                                         │  │ │Changes││
│ │Actions│ │  ├─────────────────────────────────────────┤  │ │       ││
│ │      │ │  │  Input Bar（消息输入区）                  │  │ └───────┘│
│ └──────┘ │  │  [📎] [输入框................] [发送]    │  │           │
│          │  └─────────────────────────────────────────┘  │           │
├──────────┴───────────────────────────────────────────────┴───────────┤
│  BottomPanel（可折叠）                                                │
│  [Terminal Tabs] [terminal1 ×] [terminal2 ×]                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ $ npm install                                                   │ │
│  │ added 128 packages...                                           │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

**布局特点**：
- **Sidebar（左侧）**：Session 列表 + 沙箱列表 + 快捷操作，可折叠
- **Main Content（中间）**：根据路由显示 Chat/Terminal/Files/Diff 等视图
- **Right Panel（右侧）**：Todo 列表 + 上下文信息 + 文件变更摘要，可折叠
- **Bottom Panel（底部）**：终端标签页，可折叠可拖拽调整高度
- **Status Bar（顶部）**：全局状态、Agent/Model 选择、token 使用量

---

## 路由结构

```
/                                    → 重定向到最近的 session 或新建引导
/session/:sessionId                  → 对话主界面（Chat 视图）
/session/:sessionId/terminal         → 终端全屏视图
/session/:sessionId/files            → 文件浏览器
/session/:sessionId/files/:path      → 文件查看/编辑
/session/:sessionId/diff             → 文件变更 Diff 视图
/session/:sessionId/diff/:messageId  → 某条消息的 Diff 详情
/sandbox                             → 沙箱管理（独立页面）
/settings                            → 全局设置（Agent、模型、MCP、Skill）
/settings/agents                     → Agent 配置
/settings/mcp                        → MCP 服务器管理
/settings/skills                     → Skill 管理
```

URL 搜索参数：
- `?agent=build` — 指定 Agent
- `?model=anthropic/claude-sonnet-4` — 指定模型
- `?cmd=review` — 从命令模板发起

---

## 状态管理

### Store 划分

```typescript
// stores/session.ts — Session + Message 状态
interface SessionStore {
  sessions: Session[]
  currentSessionId: string | null
  messages: Map<string, MessageWithParts[]>  // sessionId → messages
  // actions
  createSession: () => Promise<Session>
  deleteSession: (id: string) => Promise<void>
  switchSession: (id: string) => void
  sendMessage: (text: string, options?: SendOptions) => Promise<void>
  abortSession: (id: string) => Promise<void>
  revertToMessage: (sessionId: string, messageId: string) => Promise<void>
}

// stores/sandbox.ts — 沙箱状态（保留现有逻辑）
interface SandboxStore {
  containers: ContainerInfo[]
  selectedId: string | null
  // actions
  create: (name: string, image?: string) => Promise<void>
  remove: (id: string) => Promise<void>
  start: (id: string) => Promise<void>
  stop: (id: string) => Promise<void>
}

// stores/permission.ts — 权限请求队列
interface PermissionStore {
  pending: PermissionRequest[]
  // actions
  reply: (id: string, action: "once" | "always" | "reject") => Promise<void>
}

// stores/question.ts — LLM 问答队列
interface QuestionStore {
  pending: QuestionRequest[]
  // actions
  reply: (id: string, answers: Record<string, string>) => Promise<void>
}

// stores/ui.ts — UI 状态
interface UIStore {
  sidebarOpen: boolean
  rightPanelOpen: boolean
  bottomPanelOpen: boolean
  bottomPanelHeight: number  // px
  theme: "light" | "dark" | "system"
  commandPaletteOpen: boolean
}

// stores/terminal.ts — 终端标签状态
interface TerminalStore {
  tabs: TerminalTab[]
  activeTabId: string | null
  // actions
  openTerminal: (containerId: string) => void
  closeTab: (tabId: string) => void
  setActive: (tabId: string) => void
}
```

### TanStack Query 用法

```typescript
// 需要服务端数据的场景全部用 TanStack Query
const { data: sessions } = useQuery({ queryKey: ["sessions"], queryFn: api.listSessions })
const { data: messages } = useQuery({
  queryKey: ["messages", sessionId],
  queryFn: () => api.getMessages(sessionId),
  enabled: !!sessionId,
})
const { data: config } = useQuery({ queryKey: ["config"], queryFn: api.getConfig })
const { data: agents } = useQuery({ queryKey: ["agents"], queryFn: api.listAgents })
const { data: skills } = useQuery({ queryKey: ["skills"], queryFn: api.listSkills })
const { data: containers } = useQuery({
  queryKey: ["containers"],
  queryFn: api.listContainers,
  refetchInterval: 5000,  // 保留现有 5s 轮询
})
const { data: diff } = useQuery({
  queryKey: ["diff", sessionId],
  queryFn: () => api.getSessionDiff(sessionId),
  enabled: !!sessionId,
})
const { data: todo } = useQuery({
  queryKey: ["todo", sessionId],
  queryFn: () => api.getTodo(sessionId),
  enabled: !!sessionId,
})

// mutations
const sendMessage = useMutation({
  mutationFn: (text: string) => api.sendMessageAsync(sessionId, text),
  // 不需要 onSuccess invalidate，靠 SSE 事件更新
})
```

---

## 通信层

### REST API 客户端

```typescript
// services/api.ts — 扩展现有 API 客户端

const api = {
  // ===== 现有（保留） =====
  createContainer: (name: string, image?: string) => POST("/api/containers", { name, image }),
  listContainers: () => GET("/api/containers"),
  getContainer: (id: string) => GET(`/api/containers/${id}`),
  deleteContainer: (id: string) => DELETE(`/api/containers/${id}`),
  stopContainer: (id: string) => POST(`/api/containers/${id}/stop`),
  startContainer: (id: string) => POST(`/api/containers/${id}/start`),

  // ===== 新增：OpenAgent API =====
  // Session
  createSession: () => POST("/api/agent/session"),
  listSessions: () => GET("/api/agent/session"),
  getSession: (id: string) => GET(`/api/agent/session/${id}`),
  deleteSession: (id: string) => DELETE(`/api/agent/session/${id}`),
  updateSession: (id: string, data: Partial<Session>) => PATCH(`/api/agent/session/${id}`, data),

  // 消息
  getMessages: (sessionId: string) => GET(`/api/agent/session/${sessionId}/message`),
  sendMessage: (sessionId: string, text: string) => POST(`/api/agent/session/${sessionId}/message`, { text }),
  sendMessageAsync: (sessionId: string, text: string) => POST(`/api/agent/session/${sessionId}/prompt_async`, { text }),
  abortSession: (sessionId: string) => POST(`/api/agent/session/${sessionId}/abort`),

  // Compaction
  summarize: (sessionId: string) => POST(`/api/agent/session/${sessionId}/summarize`),

  // Revert
  revert: (sessionId: string, messageId: string) => POST(`/api/agent/session/${sessionId}/revert/${messageId}`),
  unrevert: (sessionId: string) => POST(`/api/agent/session/${sessionId}/unrevert`),

  // Command
  executeCommand: (sessionId: string, cmd: string, args?: string) =>
    POST(`/api/agent/session/${sessionId}/command`, { command: cmd, arguments: args }),

  // Todo
  getTodo: (sessionId: string) => GET(`/api/agent/session/${sessionId}/todo`),

  // Diff
  getSessionDiff: (sessionId: string) => GET(`/api/agent/session/${sessionId}/diff`),

  // 权限与问答
  replyPermission: (id: string, action: string) => POST(`/api/agent/permission/${id}`, { action }),
  replyQuestion: (id: string, answers: Record<string, string>) => POST(`/api/agent/question/${id}`, { answers }),

  // 元数据
  getConfig: () => GET("/api/agent/config"),
  listAgents: () => GET("/api/agent/agent"),
  listSkills: () => GET("/api/agent/skill"),
  listCommands: () => GET("/api/agent/command"),
  getMcpStatus: () => GET("/api/agent/mcp"),
  connectMcp: (name: string) => POST(`/api/agent/mcp/${name}/connect`),
  disconnectMcp: (name: string) => POST(`/api/agent/mcp/${name}/disconnect`),
}
```

### SSE 事件流

```typescript
// services/sse.ts — SSE 连接管理

class SSEClient {
  private eventSource: EventSource | null = null
  private handlers: Map<string, Set<(data: any) => void>> = new Map()

  connect(url: string = "/api/agent/event") {
    this.eventSource = new EventSource(url)
    this.eventSource.onmessage = (event) => {
      const { type, data } = JSON.parse(event.data)
      this.dispatch(type, data)
    }
    this.eventSource.onerror = () => {
      // 3 秒后自动重连
      setTimeout(() => this.connect(url), 3000)
    }
  }

  on(event: string, handler: (data: any) => void) { ... }
  off(event: string, handler: (data: any) => void) { ... }
  private dispatch(event: string, data: any) { ... }
}
```

详见 [SSE 事件驱动架构](#sse-事件驱动架构)。

### WebSocket（保留现有）

终端 PTY 通信保留现有 `useWebSocket` hook，无需修改。

---

## 功能模块详解

### M1: Session 管理

**对应后端**：`POST/GET/DELETE/PATCH /api/agent/session`

#### 功能清单

| 功能 | 描述 | 交互方式 |
|------|------|----------|
| Session 列表 | 按时间倒序显示所有 Session | Sidebar 列表 |
| 创建 Session | 点击 "New Chat" 按钮 | Sidebar 顶部按钮 |
| 切换 Session | 点击列表项 | 路由切换 `/session/:id` |
| 删除 Session | 右键菜单或滑动删除 | 确认弹窗 |
| 重命名 Session | 双击标题编辑 | 内联编辑 |
| Session 摘要 | 显示 additions/deletions/files 统计 | 列表项副标题 |
| Session 分叉 | 从某条消息创建新分支 | 消息右键菜单 "Fork here" |
| Session 搜索 | 按标题/内容搜索历史 Session | Sidebar 搜索框 |

#### Session 列表项展示

```
┌──────────────────────────────────────┐
│ 📝 Fix login page bug               │  ← 自动生成的标题
│ 2 min ago · claude-sonnet            │  ← 时间 + 模型
│ +42 -12 · 3 files                    │  ← diff 统计（绿/红）
└──────────────────────────────────────┘
```

#### Session 状态指示

| 状态 | 显示 |
|------|------|
| idle | 无特殊标记 |
| busy | 脉冲动画圆点 🟢 |
| retry | 黄色圆点 + "Retrying..." 文字 |
| error | 红色圆点 |
| compacting | 蓝色圆点 + "Compacting..." |

---

### M2: AI 对话界面

**对应后端**：`POST /api/agent/session/:id/message`, `POST /api/agent/session/:id/prompt_async`, SSE 事件流

这是最核心的新增模块。

#### 功能清单

| 功能 | 描述 | 实现方式 |
|------|------|----------|
| 消息输入 | 多行文本输入框，支持 Shift+Enter 换行 | `<textarea>` 自动扩展高度 |
| 发送消息 | Enter 发送，调用 `prompt_async` 异步 API | REST + SSE 更新 |
| 流式响应 | LLM 输出实时逐字显示 | SSE `message.text_delta` 事件 |
| 取消生成 | 点击 Stop 按钮或 Esc 键 | `POST /session/:id/abort` |
| 消息历史 | 滚动查看全部对话历史 | 虚拟滚动（消息多时） |
| 自动滚动 | 新消息时自动滚到底部，手动滚动时暂停 | IntersectionObserver |
| Markdown 渲染 | 渲染 LLM 输出的 Markdown、代码块、表格 | react-markdown |
| 代码高亮 | 代码块语法高亮 + 复制按钮 | rehype-highlight |
| 思维过程 | 显示 reasoning/thinking 部分（可折叠） | 折叠面板，默认收起 |
| 消息重试 | 重新发送某条消息 | 消息操作菜单 |
| 消息编辑 | 编辑已发送的消息并重新生成 | 消息操作菜单 |
| 撤销修改 | 撤销 LLM 对文件的修改（revert） | 消息操作菜单 |
| 文件附件 | 拖拽或粘贴图片/文件 | 输入区 dropzone |
| 斜杠命令 | 输入 `/` 弹出命令列表 | 自动补全下拉 |
| @文件引用 | 输入 `@` 引用文件路径 | 文件路径自动补全 |
| Agent 切换 | 在输入区选择当前 Agent | 下拉选择器 |
| Variant 选择 | 选择 reasoning effort（low/medium/high） | 下拉选择器 |

#### 输入区详细设计

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Agent: build ▾] [Variant: medium ▾]                     [📎 附件] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  输入消息...（支持 Markdown）                                       │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ [/ 命令] [@ 文件]                                    [⌘↵ 发送]     │
└─────────────────────────────────────────────────────────────────────┘
```

生成中状态：
```
┌─────────────────────────────────────────────────────────────────────┐
│ ⏳ Agent is working...                        [■ Stop] [⏸ Pause]   │
│ Step 3 · Reading src/App.tsx                                        │
└─────────────────────────────────────────────────────────────────────┘
```

#### 斜杠命令自动补全

输入 `/` 后弹出命令列表：

```
┌────────────────────────────────────┐
│ /review  Review code changes       │
│ /commit  Create a git commit       │
│ /init    Initialize project        │
│ /help    Show available commands   │
│ /compact Trigger context compact   │
└────────────────────────────────────┘
```

数据来源：`GET /api/agent/command`

---

### M3: 消息渲染系统

每条消息由多个 Part 组成，需要按类型分别渲染。

#### Part 渲染器映射

| Part 类型 | 渲染组件 | 展示方式 |
|-----------|----------|----------|
| `text` | `<TextPart>` | Markdown 渲染 |
| `reasoning` | `<ReasoningPart>` | 可折叠面板，浅色背景，斜体 |
| `tool` (pending) | `<ToolPart>` | 旋转加载图标 + 工具名 |
| `tool` (running) | `<ToolPart>` | 脉冲动画 + 工具名 + 输入参数 |
| `tool` (completed) | `<ToolPart>` | 绿色勾 + 工具名 + 可展开输出 |
| `tool` (error) | `<ToolPart>` | 红色叉 + 错误信息 |
| `step-start` | `<StepDivider>` | 细线分隔符 "Step N" |
| `step-finish` | `<StepSummary>` | Token 使用量 + 耗时 + cost |
| `compaction` | `<CompactionBadge>` | 蓝色横幅 "Context compacted" |
| `subtask` | `<SubtaskPart>` | 子 Agent 名称 + 状态 |
| `patch` | `<PatchPart>` | 文件变更列表，可点击查看 diff |
| `file` | `<FilePart>` | 图片预览 / 文件图标+名称 |
| `agent` | `<AgentSwitchBadge>` | "Switched to agent: plan" |
| `retry` | `<RetryBadge>` | "Retrying... attempt 2" |

#### 消息气泡结构

**User 消息**：
```
┌──────────────────────────────────────┐
│                          You         │
│                                      │
│  Fix the login bug in auth.ts        │
│                                      │
│                         2:30 PM  ✎ ↺ │
└──────────────────────────────────────┘
```

**Assistant 消息**：
```
┌──────────────────────────────────────────────────────┐
│ claude-sonnet · build                                │
│                                                      │
│ ▸ Thinking... (click to expand)                      │  ← ReasoningPart (折叠)
│                                                      │
│ I'll fix the login bug. Let me read the file first.  │  ← TextPart
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 📖 read  src/auth.ts                        ✓   │ │  ← ToolPart (completed)
│ │ ▸ Show output (245 lines)                       │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌──────────────────────────────────────────────────┐ │
│ │ ✏️ edit  src/auth.ts                        ✓   │ │  ← ToolPart (completed)
│ │ ▸ Show diff                                     │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ I've fixed the bug by adding null check on line 42.  │  ← TextPart
│                                                      │
│ ──── Step 1 · 1,234 in / 856 out · $0.003 ────────  │  ← StepFinishPart
│                                                      │
│                                    2:31 PM  ↩ Revert │
└──────────────────────────────────────────────────────┘
```

#### ToolPart 展开状态详细设计

**bash 工具**：
```
┌─────────────────────────────────────────────────────────────────┐
│ 🖥️ bash                                               ✓ 0.8s  │
│ $ npm install express                                          │
├─────────────────────────────────────────────────────────────────┤
│ added 64 packages, and audited 65 packages in 3s              │
│ found 0 vulnerabilities                                        │
│                                              [Copy] [Full ▾]   │
└─────────────────────────────────────────────────────────────────┘
```

**read 工具**：
```
┌─────────────────────────────────────────────────────────────────┐
│ 📖 read  src/auth.ts                                  ✓ 0.2s  │
├─────────────────────────────────────────────────────────────────┤
│  1 │ import { hash } from 'bcrypt'                             │
│  2 │ import { db } from './database'                           │
│  3 │                                                           │
│ ... 242 more lines                          [Open File] [Copy] │
└─────────────────────────────────────────────────────────────────┘
```

**edit 工具**（显示 diff）：
```
┌─────────────────────────────────────────────────────────────────┐
│ ✏️ edit  src/auth.ts                                  ✓ 0.1s  │
├─────────────────────────────────────────────────────────────────┤
│ @@ -40,3 +40,5 @@                                              │
│   const user = await db.findUser(email)                        │
│ - return user.token                                            │
│ + if (!user) return null                                       │
│ + return user.token                                            │
│                                              [Open File] [Copy] │
└─────────────────────────────────────────────────────────────────┘
```

**glob/grep 工具**：
```
┌─────────────────────────────────────────────────────────────────┐
│ 🔍 grep  pattern: "TODO"  path: src/                  ✓ 0.3s  │
├─────────────────────────────────────────────────────────────────┤
│ src/auth.ts:15:   // TODO: add rate limiting                   │
│ src/api.ts:42:    // TODO: validate input                      │
│ src/utils.ts:8:   // TODO: use crypto.randomUUID               │
│                                               3 matches [Copy] │
└─────────────────────────────────────────────────────────────────┘
```

**task 工具**（子 Agent）：
```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 task  agent: explore                               ✓ 4.2s  │
│ "Find all error handling patterns in the codebase"             │
├─────────────────────────────────────────────────────────────────┤
│ ▸ Show subtask output (click to expand)                        │
└─────────────────────────────────────────────────────────────────┘
```

**工具执行中**：
```
┌─────────────────────────────────────────────────────────────────┐
│ 🖥️ bash                                              ⟳ 12s... │
│ $ npm run build                                                │
├─────────────────────────────────────────────────────────────────┤
│ Building...                                                    │
│ ████████████████░░░░░░░░░░░░ 62%                               │
│                                                     [■ Cancel] │
└─────────────────────────────────────────────────────────────────┘
```

---

### M4: 工具执行可视化

**对应 SSE 事件**：`tool.running`, `tool.completed`, `tool.error`

#### 功能清单

| 功能 | 描述 |
|------|------|
| 实时状态 | 工具从 pending → running → completed/error 的状态动画转换 |
| 输入参数展示 | 展开显示工具的输入参数（JSON 格式化） |
| 输出预览 | 完成后展示输出的前 20 行，可展开查看全部 |
| 截断提示 | 输出被截断时显示 "... N lines truncated" + 查看完整输出按钮 |
| Diff 预览 | edit/apply_patch 工具显示内联 diff |
| 文件跳转 | 点击文件路径跳转到文件浏览器 |
| 时间统计 | 显示每个工具的执行耗时 |
| 错误高亮 | 错误状态红色背景 + 错误消息 |
| 批量工具 | batch 工具显示为折叠的并行执行列表 |

---

### M5: 权限交互

**对应后端**：SSE `permission.asked` 事件 → `POST /api/agent/permission/:id`

当 Agent 需要执行敏感操作时，后端发送权限请求，前端显示交互式弹窗。

#### 权限弹窗设计

```
┌───────────────────────────────────────────────────────┐
│ ⚠️ Permission Required                                │
├───────────────────────────────────────────────────────┤
│                                                       │
│ Agent wants to execute:                               │
│                                                       │
│   bash: rm -rf /tmp/cache                             │
│                                                       │
│ ┌───────────────────────────────────────────────────┐ │
│ │ ☐ Always allow `bash rm *` for this session       │ │
│ └───────────────────────────────────────────────────┘ │
│                                                       │
│      [Reject]          [Allow Once]    [Allow Always] │
└───────────────────────────────────────────────────────┘
```

#### Doom Loop 弹窗

```
┌───────────────────────────────────────────────────────┐
│ 🔄 Possible Loop Detected                             │
├───────────────────────────────────────────────────────┤
│                                                       │
│ Agent has called the same tool 3 times with           │
│ identical arguments:                                  │
│                                                       │
│   bash: git status                                    │
│                                                       │
│ This may indicate the agent is stuck in a loop.       │
│                                                       │
│              [Stop Agent]           [Continue]         │
└───────────────────────────────────────────────────────┘
```

#### 功能清单

| 功能 | 描述 |
|------|------|
| 权限弹窗 | 模态弹窗显示工具名 + 参数 + 操作按钮 |
| 三种操作 | Allow Once / Allow Always / Reject |
| 消息内嵌 | 在对话流中也显示权限卡片（已允许/已拒绝） |
| Doom Loop | 特殊弹窗，提示可能的死循环 |
| 超时处理 | 超过 60s 无回复自动 reject（前端倒计时） |
| 批量操作 | 多个权限请求排队时可批量 Allow Always |

---

### M6: 用户问答交互

**对应后端**：SSE `question.asked` 事件 → `POST /api/agent/question/:id`

LLM 通过 question 工具向用户提问。

#### 问答卡片设计

```
┌───────────────────────────────────────────────────────┐
│ ❓ Agent is asking you a question                      │
├───────────────────────────────────────────────────────┤
│                                                       │
│ Which authentication method should we use?            │
│                                                       │
│ ○ JWT tokens (Recommended)                            │
│   Stateless, good for distributed systems             │
│                                                       │
│ ○ Session cookies                                     │
│   Traditional, simpler implementation                 │
│                                                       │
│ ○ OAuth 2.0                                           │
│   Third-party login support                           │
│                                                       │
│ ○ Other: [________________]                           │
│                                                       │
│                                           [Submit ▶]  │
└───────────────────────────────────────────────────────┘
```

#### 功能清单

| 功能 | 描述 |
|------|------|
| 单选/多选 | 根据 `multi_select` 字段切换 radio/checkbox |
| 自定义输入 | 每个问题自动附带 "Other" 选项 + 文本输入 |
| 多问题 | 1-4 个问题按顺序展示在同一卡片中 |
| 消息内嵌 | 问答完成后在对话流中显示为已回答卡片 |
| 键盘导航 | 方向键选择，Enter 提交 |

---

### M7: Todo 任务面板

**对应后端**：`GET /api/agent/session/:id/todo`, SSE `todo.updated` 事件

在右侧面板显示 Agent 创建的任务列表。

#### 面板设计

```
┌── Todo ──────────────────────────┐
│                                  │
│ ✅ Set up project structure      │
│ ✅ Install dependencies          │
│ ⏳ Fix authentication bug ←      │  ← 当前进行中（高亮）
│ ⬜ Add unit tests                │
│ ⬜ Update documentation          │
│                                  │
│ 2/5 completed                    │
│ ████████░░░░░░░░░░░░ 40%        │
└──────────────────────────────────┘
```

#### 功能清单

| 功能 | 描述 |
|------|------|
| 实时更新 | SSE 事件驱动，Agent 更新 todo 时自动刷新 |
| 状态颜色 | pending=灰, in_progress=蓝(脉冲), completed=绿(勾) |
| 进度条 | 底部显示总体完成百分比 |
| 折叠完成项 | 可选择隐藏已完成项 |
| 只读展示 | 用户不直接编辑，由 Agent 管理 |

---

### M8: Plan 模式

**对应后端**：Agent mode 切换（build ↔ plan），`tool/plan.py`

#### 功能清单

| 功能 | 描述 |
|------|------|
| 模式指示器 | Status Bar 显示当前模式（Build / Plan） |
| 模式横幅 | Plan 模式下对话区顶部显示蓝色横幅 "Plan Mode - Read Only" |
| Plan 文件编辑 | 显示 `.openagent/plans/*.md` 的内容 |
| Plan 审批 | Agent 提交 plan 后，用户可选 "Approve" / "Edit" / "Reject" |
| 模式切换动画 | build↔plan 切换时的视觉提示 |

#### Plan 审批卡片

```
┌───────────────────────────────────────────────────────┐
│ 📋 Plan: Fix Authentication System                     │
├───────────────────────────────────────────────────────┤
│                                                       │
│ ## Steps                                              │
│ 1. Add input validation to login endpoint             │
│ 2. Fix null pointer in token verification             │
│ 3. Add rate limiting middleware                       │
│ 4. Write unit tests for auth flow                     │
│                                                       │
│ ## Files to modify                                    │
│ - src/auth/login.ts                                   │
│ - src/middleware/rateLimit.ts (new)                    │
│ - tests/auth.test.ts (new)                            │
│                                                       │
│     [Reject]          [Edit Plan]      [Approve ▶]   │
└───────────────────────────────────────────────────────┘
```

---

### M9: 上下文管理可视化

**对应后端**：compaction 系统、token 追踪

#### 功能清单

| 功能 | 描述 | 展示位置 |
|------|------|----------|
| Token 使用量 | 当前 session 的累计 input/output/cache token | Status Bar |
| 上下文进度条 | 已用 token / 模型上限 的可视化进度条 | Status Bar 或右侧面板 |
| Compaction 通知 | "Context compacted" 横幅在对话流中 | 对话区 |
| Compaction 摘要 | 点击横幅可查看压缩摘要内容 | 弹窗 |
| 手动 Compact | 按钮触发手动压缩 | 对话区顶部或命令面板 |
| Cost 统计 | 累计花费（基于 token 和模型定价） | 右侧面板 |
| 每步 Token | 每个 step-finish 显示该步的 token 使用 | 对话流内 |

#### 上下文进度条设计

```
┌── Context ───────────────────────────────────────────┐
│ Token Usage: 85,432 / 200,000                        │
│ ████████████████████████████████████░░░░░░░░░ 42.7%  │
│                                                      │
│ Input: 62,100  Output: 18,200  Cache: 5,132          │
│ Cost: $0.24                                          │
│                                                      │
│ Compactions: 2  Pruned tools: 14                     │
│                              [Compact Now]            │
└──────────────────────────────────────────────────────┘
```

---

### M10: 沙箱管理（增强）

**保留现有功能**，新增：

| 新增功能 | 描述 |
|----------|------|
| Session 绑定 | 显示哪个 Session 在使用哪个沙箱 |
| 系统信息 | 显示 CPU/内存/磁盘使用率（调用 `/system_info`） |
| 日志查看 | 查看容器日志 |
| 批量操作 | 批量停止/删除沙箱 |
| 镜像选择 | 创建时选择不同的沙箱镜像 |
| 资源配置 | 创建时设置内存/CPU 限制 |

#### 增强后的沙箱卡片

```
┌─────────────────────────────────────────────────────┐
│ 🟢 agent-dev-sandbox                       Running  │
│ Session: Fix login bug · 3 min ago                  │
│ CPU: 12%  MEM: 128/512MB  DISK: 45/1GB             │
│ Image: openbox-sandbox:latest                       │
│                                                     │
│        [Terminal]  [Files]  [Stop]  [🗑️]            │
└─────────────────────────────────────────────────────┘
```

---

### M11: 终端（增强）

**保留现有功能**（xterm.js + WebSocket PTY），新增：

| 新增功能 | 描述 |
|----------|------|
| 底部面板 | 终端从全屏改为底部可折叠面板 |
| 拖拽调整 | 面板高度可拖拽调整 |
| 多标签 | 保留现有多标签功能 |
| 分屏 | 支持左右分屏终端 |
| 搜索 | 终端内文本搜索（Ctrl+Shift+F） |
| 快捷键 | Ctrl+` 切换终端可见性 |
| Agent 终端 | Agent 执行 bash 工具时关联对应终端标签 |

---

### M12: 文件浏览器

**对应后端**：`POST /api/containers/:id/files/list`, Action Server `/upload`, `/download`

#### 功能清单

| 功能 | 描述 |
|------|------|
| 目录树 | 左侧树状文件目录（懒加载） |
| 文件列表 | 右侧文件列表（名称、大小、修改时间） |
| 文件预览 | 代码文件语法高亮预览 |
| 文件上传 | 拖拽上传或选择文件 |
| 文件下载 | 点击下载单文件或目录（zip） |
| 面包屑导航 | 路径面包屑，可点击跳转 |
| 搜索 | 按文件名搜索 |
| 新建 | 新建文件/目录 |
| Agent 修改高亮 | 被 Agent 修改过的文件标注 |

#### 文件浏览器布局

```
┌── Files ─────────────────────────────────────────────────────┐
│ /workspace > src > auth >                      [↑] [Search] │
├──────────────────┬───────────────────────────────────────────┤
│ 📁 src/          │  Name          Size     Modified          │
│  📁 auth/    ←   │  📄 login.ts   2.4KB   2 min ago  ★     │  ← ★ = Agent 修改过
│  📁 api/         │  📄 verify.ts  1.1KB   5 min ago  ★     │
│  📁 utils/       │  📄 types.ts   890B    1 hour ago        │
│ 📁 tests/        │                                          │
│ 📄 package.json  │                                          │
│ 📄 tsconfig.json │                                          │
└──────────────────┴───────────────────────────────────────────┘
```

---

### M13: Diff 查看器

**对应后端**：`GET /api/agent/session/:id/diff`, `GET /api/agent/session/:id/diff/:messageId`

#### 功能清单

| 功能 | 描述 |
|------|------|
| Session Diff | 整个 Session 的文件变更总览 |
| Message Diff | 某条消息的文件变更详情 |
| Unified/Split 视图 | 切换统一 diff 和分栏 diff |
| 行号 | 显示变更前后的行号 |
| 语法高亮 | diff 中的代码语法高亮 |
| 文件筛选 | 按文件名过滤变更文件 |
| 统计摘要 | 总计 additions/deletions/files 数量 |
| Revert 按钮 | 按消息粒度撤销修改 |

#### Diff 视图布局

```
┌── Changes ───────────────────────────────────────────────────┐
│ 3 files changed  +42 -12                    [Unified|Split]  │
├──────────────────────────────────────────────────────────────┤
│ 📄 src/auth/login.ts  +25 -8                      [Revert]  │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ @@ -38,6 +38,10 @@                                    │   │
│ │  38 │ const user = await db.findUser(email)            │   │
│ │  39 │                                                  │   │
│ │  40 │-  return user.token                              │   │
│ │  40 │+  if (!user) {                                   │   │
│ │  41 │+    throw new AuthError("User not found")        │   │
│ │  42 │+  }                                              │   │
│ │  43 │+  return user.token                              │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ 📄 src/middleware/rateLimit.ts (new)  +15                    │
│ ...                                                          │
└──────────────────────────────────────────────────────────────┘
```

---

### M14: Agent 与模型配置

**对应后端**：`GET /api/agent/agent`, `GET /api/agent/config`

#### 功能清单

| 功能 | 描述 |
|------|------|
| Agent 列表 | 显示所有可用 Agent（build, plan, explore 等） |
| 当前 Agent | 显示当前 Session 使用的 Agent |
| Agent 详情 | 查看 Agent 的 prompt、可用工具、模型配置 |
| 模型选择 | 在支持的模型之间切换 |
| Variant 选择 | 选择 reasoning effort 级别 |
| Temperature | 显示当前 Agent 的 temperature 设置 |
| 工具开关 | 启用/禁用特定工具 |

---

### M15: Skill 管理

**对应后端**：`GET /api/agent/skill`

#### 功能清单

| 功能 | 描述 |
|------|------|
| Skill 列表 | 显示所有已发现的 Skill（名称、描述、来源） |
| Skill 详情 | 查看 Skill 的完整内容（Markdown 渲染） |
| 来源标注 | 区分全局/项目/远程 Skill |
| 搜索 | 按名称/描述搜索 |

---

### M16: MCP 服务器管理

**对应后端**：`GET /api/agent/mcp`, `POST /api/agent/mcp/:name/connect`, `POST /api/agent/mcp/:name/disconnect`

#### 功能清单

| 功能 | 描述 |
|------|------|
| 服务器列表 | 显示所有已配置的 MCP 服务器 |
| 连接状态 | 显示每个服务器的连接状态（connected/disconnected/error） |
| 工具列表 | 展开显示每个服务器提供的工具 |
| 连接/断开 | 一键连接/断开 MCP 服务器 |
| 错误信息 | 显示连接失败的错误详情 |

#### MCP 面板设计

```
┌── MCP Servers ───────────────────────────────────────────────┐
│                                                              │
│ 🟢 filesystem (stdio)                         [Disconnect]   │
│    Tools: read_file, write_file, list_dir, search            │
│                                                              │
│ 🔴 github (remote)                              [Connect]    │
│    Error: Connection timeout                                 │
│                                                              │
│ 🟢 database (stdio)                           [Disconnect]   │
│    Tools: query, list_tables, describe_table                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### M17: 命令面板

全局命令面板，通过 `Cmd+K` / `Ctrl+K` 打开。

#### 功能清单

| 功能 | 描述 |
|------|------|
| 全局搜索 | 搜索 Sessions、命令、文件、工具 |
| 斜杠命令 | 列出所有可用的 `/command` |
| 快捷操作 | New Session, Compact Context, Switch Agent 等 |
| 最近 Session | 快速切换最近的 Session |
| 键盘导航 | 方向键选择，Enter 执行 |

#### 命令面板设计

```
┌─────────────────────────────────────────────────────────────┐
│ 🔍 Type a command or search...                              │
├─────────────────────────────────────────────────────────────┤
│ Sessions                                                    │
│   📝 Fix login page bug                      2 min ago      │
│   📝 Add user authentication                 1 hour ago     │
│                                                             │
│ Commands                                                    │
│   /review   Review code changes                             │
│   /commit   Create a git commit                             │
│   /compact  Compact context                                 │
│                                                             │
│ Actions                                                     │
│   ＋ New Session                                Ctrl+N      │
│   🔄 Switch Agent                              Ctrl+Shift+A │
│   ⚙  Settings                                 Ctrl+,       │
└─────────────────────────────────────────────────────────────┘
```

---

### M18: 全局通知与状态栏

#### Status Bar（顶部）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🤖 OpenAgent  │ Fix login bug │ Agent: build ▾ │ claude-sonnet ▾   │
│               │               │ Variant: med ▾ │ 85K/200K tokens   │
│               │               │                │ $0.24  │ 🟢 Ready │
└──────────────────────────────────────────────────────────────────────┘
```

#### 通知系统

| 通知类型 | 触发条件 | 展示方式 |
|----------|----------|----------|
| 权限请求 | Agent 需要权限 | 模态弹窗 + toast |
| 问答请求 | Agent 提问 | 对话流内嵌卡片 |
| 错误 | API 错误、WebSocket 断连 | 红色 toast，3s 后消失 |
| 重试中 | Agent 遇到速率限制 | 黄色 toast + 倒计时 |
| Compaction | 上下文压缩完成 | 蓝色 toast |
| 完成 | Agent 完成任务 | 绿色 toast + 桌面通知 |
| 连接状态 | SSE/WebSocket 断开重连 | Status Bar 图标变色 |

---

## SSE 事件驱动架构

前端通过 `GET /api/agent/event` 的 SSE 连接接收所有实时事件，驱动 UI 更新。

### 事件→Store 映射

```typescript
// hooks/useSSE.ts — SSE 事件分发到各 Store

function setupSSEHandlers(sse: SSEClient) {
  const sessionStore = useSessionStore.getState()
  const permissionStore = usePermissionStore.getState()
  const questionStore = useQuestionStore.getState()
  const queryClient = getQueryClient()

  // Session 状态
  sse.on("session.status", (data) => {
    sessionStore.updateStatus(data.sessionId, data.status)
  })

  // 消息更新
  sse.on("message.created", (data) => {
    sessionStore.addMessage(data.sessionId, data.message)
  })
  sse.on("message.updated", (data) => {
    sessionStore.updateMessage(data.sessionId, data.message)
  })
  sse.on("message.text_delta", (data) => {
    sessionStore.appendTextDelta(data.sessionId, data.messageId, data.partId, data.text)
  })

  // Part 更新
  sse.on("part.created", (data) => {
    sessionStore.addPart(data.sessionId, data.messageId, data.part)
  })
  sse.on("part.updated", (data) => {
    sessionStore.updatePart(data.sessionId, data.messageId, data.part)
  })
  sse.on("part.delta", (data) => {
    sessionStore.appendPartDelta(data.sessionId, data.messageId, data.partId, data.delta)
  })

  // 工具事件
  sse.on("tool.running", (data) => {
    sessionStore.updateToolStatus(data.sessionId, data.partId, "running", data)
  })
  sse.on("tool.completed", (data) => {
    sessionStore.updateToolStatus(data.sessionId, data.partId, "completed", data)
  })
  sse.on("tool.error", (data) => {
    sessionStore.updateToolStatus(data.sessionId, data.partId, "error", data)
  })

  // 权限
  sse.on("permission.asked", (data) => {
    permissionStore.addPending(data)
  })

  // 问答
  sse.on("question.asked", (data) => {
    questionStore.addPending(data)
  })

  // Todo
  sse.on("todo.updated", (data) => {
    queryClient.invalidateQueries({ queryKey: ["todo", data.sessionId] })
  })

  // Diff
  sse.on("session.diff", (data) => {
    queryClient.invalidateQueries({ queryKey: ["diff", data.sessionId] })
  })

  // 错误
  sse.on("session.error", (data) => {
    toast.error(data.error.message)
  })

  // Compaction
  sse.on("session.compaction.start", (data) => {
    sessionStore.updateStatus(data.sessionId, { type: "compacting" })
  })
  sse.on("session.compaction.complete", (data) => {
    sessionStore.updateStatus(data.sessionId, { type: "idle" })
    toast.info("Context compacted")
  })
}
```

### SSE 事件完整列表

| 事件名 | 数据 | 触发前端操作 |
|--------|------|-------------|
| `session.status` | `{ sessionId, status }` | 更新 Session 状态指示器 |
| `session.title` | `{ sessionId, title }` | 更新 Session 列表标题 |
| `session.error` | `{ sessionId, error }` | 显示错误 toast |
| `session.diff` | `{ sessionId, diff }` | 刷新 Diff 查看器 |
| `session.compaction.start` | `{ sessionId }` | 显示 compacting 状态 |
| `session.compaction.complete` | `{ sessionId }` | 恢复 idle，显示 compaction 横幅 |
| `message.created` | `{ sessionId, message }` | 添加新消息到对话流 |
| `message.updated` | `{ sessionId, message }` | 更新消息（finish, tokens, error） |
| `message.text_delta` | `{ sessionId, messageId, partId, text }` | 追加文字到流式输出 |
| `part.created` | `{ sessionId, messageId, part }` | 添加新 Part（tool/reasoning/text 等） |
| `part.updated` | `{ sessionId, messageId, part }` | 更新 Part 状态 |
| `part.delta` | `{ sessionId, messageId, partId, delta }` | 追加 reasoning/text delta |
| `tool.running` | `{ sessionId, partId, tool, input }` | ToolPart 切换为运行状态 |
| `tool.completed` | `{ sessionId, partId, output, title }` | ToolPart 切换为完成状态 |
| `tool.error` | `{ sessionId, partId, error }` | ToolPart 切换为错误状态 |
| `permission.asked` | `{ id, permission, patterns, metadata }` | 弹出权限弹窗 |
| `question.asked` | `{ id, questions }` | 在对话流中插入问答卡片 |
| `todo.updated` | `{ sessionId }` | 刷新 Todo 面板 |

---

## 响应式设计

| 断点 | 布局变化 |
|------|----------|
| `≥1440px` (xl) | 三栏布局：Sidebar + Main + Right Panel |
| `1024-1439px` (lg) | 两栏布局：Sidebar + Main，Right Panel 折叠为抽屉 |
| `768-1023px` (md) | 两栏布局：Sidebar 折叠为抽屉，Bottom Panel 全宽 |
| `<768px` (sm) | 单栏布局：全部面板改为抽屉/全屏切换 |

---

## 主题系统

保留现有 CSS 自定义属性方案，扩展变量：

```css
:root {
  /* 现有变量保留 */
  --bg-primary: ...;
  --text-primary: ...;

  /* 新增：消息气泡 */
  --bubble-user: ...;
  --bubble-assistant: ...;
  --bubble-system: ...;

  /* 新增：工具状态 */
  --tool-pending: ...;
  --tool-running: ...;
  --tool-completed: ...;
  --tool-error: ...;

  /* 新增：上下文 */
  --context-bar: ...;
  --compaction-banner: ...;

  /* 新增：权限 */
  --permission-warn: ...;
  --permission-allow: ...;
  --permission-reject: ...;
}
```

---

## 实现优先级

### Phase 1：核心对话（必须）

| # | 模块 | 关键依赖 |
|---|------|----------|
| 1 | 路由 + 布局骨架 | TanStack Router |
| 2 | 状态管理基础 | Zustand stores 定义 |
| 3 | SSE 连接 + 事件分发 | SSEClient + hooks |
| 4 | Session 管理 (M1) | REST API + SSE |
| 5 | 消息输入 + 发送 (M2) | prompt_async API |
| 6 | 消息渲染 - TextPart (M3) | react-markdown |
| 7 | 消息渲染 - ToolPart (M4) | SSE tool events |
| 8 | 权限交互 (M5) | SSE + REST |
| 9 | 状态栏 (M18) | Session status |

### Phase 2：增强体验

| # | 模块 | 关键依赖 |
|---|------|----------|
| 10 | 消息渲染 - 所有 Part 类型 (M3) | Part 渲染器补全 |
| 11 | 用户问答 (M6) | SSE + REST |
| 12 | Todo 面板 (M7) | SSE + REST |
| 13 | 上下文可视化 (M9) | Token tracking |
| 14 | 斜杠命令 + @文件引用 (M2) | Command/File API |
| 15 | 终端增强 - 底部面板 (M11) | 保留现有 xterm |
| 16 | Diff 查看器 (M13) | diff2html |

### Phase 3：完整功能

| # | 模块 | 关键依赖 |
|---|------|----------|
| 17 | 文件浏览器 (M12) | Action Server API |
| 18 | Plan 模式 (M8) | Agent mode switch |
| 19 | 命令面板 (M17) | Cmd+K |
| 20 | Agent/模型配置 (M14) | Config API |
| 21 | Skill 管理 (M15) | Skill API |
| 22 | MCP 管理 (M16) | MCP API |
| 23 | 沙箱增强 (M10) | System info API |

### Phase 4：打磨

| # | 模块 |
|---|------|
| 24 | 响应式适配 |
| 25 | 动画和过渡效果 |
| 26 | 键盘快捷键完整支持 |
| 27 | 桌面通知 |
| 28 | 性能优化（虚拟滚动、消息缓存） |

---

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Cmd/Ctrl + K` | 打开命令面板 |
| `Cmd/Ctrl + N` | 新建 Session |
| `Cmd/Ctrl + Enter` | 发送消息 |
| `Escape` | 取消生成 / 关闭弹窗 |
| `Ctrl + `` ` | 切换终端面板 |
| `Cmd/Ctrl + Shift + A` | 切换 Agent |
| `Cmd/Ctrl + ,` | 打开设置 |
| `Cmd/Ctrl + [` / `]` | 切换 Session |
| `Cmd/Ctrl + Shift + F` | 终端搜索 |

---

## 目录结构（建议）

```
frontend/src/
  main.tsx
  App.tsx                           # 根组件 + QueryProvider + RouterProvider
  index.css

  routes/
    __root.tsx                      # 根布局（StatusBar + Sidebar + Outlet）
    index.tsx                       # / → 重定向
    session/
      $sessionId.tsx                # /session/:id 布局
      $sessionId.index.tsx          # Chat 视图
      $sessionId.terminal.tsx       # Terminal 视图
      $sessionId.files.tsx          # File 浏览器
      $sessionId.diff.tsx           # Diff 视图
    sandbox.tsx                     # /sandbox 沙箱管理
    settings/
      index.tsx                     # /settings
      agents.tsx                    # /settings/agents
      mcp.tsx                       # /settings/mcp
      skills.tsx                    # /settings/skills

  stores/
    session.ts                      # Session + Message Zustand store
    sandbox.ts                      # 沙箱 Zustand store
    permission.ts                   # 权限请求 store
    question.ts                     # 问答请求 store
    terminal.ts                     # 终端标签 store
    ui.ts                           # UI 状态 store

  services/
    api.ts                          # REST API 客户端（扩展现有）
    sse.ts                          # SSE 连接管理
    websocket.ts                    # WebSocket 管理（保留现有）

  hooks/
    useSSE.ts                       # SSE 事件 → Store 分发
    useWebSocket.ts                 # 保留现有
    useKeyboard.ts                  # 全局键盘快捷键
    useAutoScroll.ts                # 对话自动滚动

  components/
    layout/
      StatusBar.tsx                 # 顶部状态栏
      Sidebar.tsx                   # 左侧边栏（增强）
      RightPanel.tsx                # 右侧面板
      BottomPanel.tsx               # 底部终端面板
      CommandPalette.tsx            # Cmd+K 命令面板

    chat/
      ChatView.tsx                  # 对话主视图
      MessageList.tsx               # 消息列表（虚拟滚动）
      MessageBubble.tsx             # 单条消息气泡
      InputBar.tsx                  # 消息输入区
      SlashCommand.tsx              # 斜杠命令自动补全
      FileMention.tsx               # @文件引用自动补全

    parts/
      TextPart.tsx                  # Markdown 文本
      ReasoningPart.tsx             # 思维过程（折叠）
      ToolPart.tsx                  # 工具执行（通用容器）
      ToolBash.tsx                  # bash 工具渲染
      ToolRead.tsx                  # read 工具渲染
      ToolEdit.tsx                  # edit 工具渲染（内联 diff）
      ToolGrep.tsx                  # grep 工具渲染
      ToolGlob.tsx                  # glob 工具渲染
      ToolTask.tsx                  # task 工具渲染（子 Agent）
      StepDivider.tsx               # step 分隔符
      StepSummary.tsx               # step 摘要（token/cost）
      CompactionBadge.tsx           # compaction 横幅
      PatchPart.tsx                 # 文件变更列表
      AgentSwitchBadge.tsx          # Agent 切换标记
      RetryBadge.tsx                # 重试标记

    permission/
      PermissionDialog.tsx          # 权限请求弹窗
      DoomLoopDialog.tsx            # Doom Loop 弹窗
      PermissionCard.tsx            # 消息内嵌权限卡片

    question/
      QuestionCard.tsx              # 问答卡片
      QuestionOption.tsx            # 单个选项

    plan/
      PlanBanner.tsx                # Plan 模式横幅
      PlanApprovalCard.tsx          # Plan 审批卡片

    todo/
      TodoPanel.tsx                 # Todo 列表面板
      TodoItem.tsx                  # 单个 Todo 项

    context/
      ContextPanel.tsx              # 上下文信息面板
      TokenProgressBar.tsx          # Token 进度条
      CostDisplay.tsx               # 费用显示

    diff/
      DiffView.tsx                  # Diff 主视图
      DiffFile.tsx                  # 单文件 Diff
      DiffSummary.tsx               # 变更统计摘要

    files/
      FileBrowser.tsx               # 文件浏览器主视图
      FileTree.tsx                  # 目录树
      FileList.tsx                  # 文件列表
      FilePreview.tsx               # 文件预览

    terminal/
      Terminal.tsx                  # 保留现有
      TerminalTabs.tsx              # 保留现有

    sandbox/
      SandboxList.tsx               # 沙箱列表（增强）
      SandboxCard.tsx               # 沙箱卡片（增强）
      CreateSandboxDialog.tsx       # 创建沙箱弹窗（增强）
      SystemInfo.tsx                # 系统信息展示

    settings/
      AgentConfig.tsx               # Agent 配置
      ModelSelector.tsx             # 模型选择器
      McpManager.tsx                # MCP 管理
      SkillList.tsx                 # Skill 列表

    ui/
      Toast.tsx                     # 通知 Toast
      Modal.tsx                     # 模态弹窗
      Dropdown.tsx                  # 下拉菜单
      Badge.tsx                     # 状态徽章
      Progress.tsx                  # 进度条
      Spinner.tsx                   # 加载旋转器
      Tooltip.tsx                   # 工具提示
      Tabs.tsx                      # 标签页

  types/
    index.ts                        # 保留现有 + 新增 Agent 类型
    session.ts                      # Session / Message / Part 类型
    agent.ts                        # Agent / Skill / MCP 类型
    permission.ts                   # Permission 类型
    question.ts                     # Question 类型
    sse.ts                          # SSE 事件类型

  lib/
    utils.ts                        # 保留现有 + 扩展
    markdown.ts                     # Markdown 处理工具
    token.ts                        # Token 估算（前端侧）
```
