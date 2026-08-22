// Wire types — mirrors the OpenBox backend contracts (backend/api/*.py).
// These are transport-level shapes shared across features; feature-internal
// view models live in each feature's own types/.

export type SessionStatus = "idle" | "busy" | "finalizing" | "retry" | "error" | "compacting"

export interface TokenUsage {
  input: number
  output: number
  cache: number
  total: number
  limit: number
  cost: number
  context: number
}

export interface Session {
  id: string
  title: string
  agent: string
  model: string
  status: SessionStatus
  created_at: string
  updated_at: string
  slug?: string
  project_id?: string
  additions?: number
  deletions?: number
  files_changed?: number
  token_usage?: TokenUsage
}

export interface Project {
  id: string
  name: string
  slug?: string
  description?: string | null
  directory?: string
  session_count?: number
  created_at?: string
  updated_at?: string
}

export type PlanStatus = "writing" | "ready" | "accepted" | "rejected"
export type ToolStatus = "pending" | "running" | "completed" | "error"

export interface TextPart {
  type: "text"
  id: string
  text: string
  synthetic?: boolean
}
export interface ReasoningPart {
  type: "reasoning"
  id: string
  text: string
}
export interface ToolPart {
  type: "tool"
  id: string
  tool: string
  status: ToolStatus
  input?: Record<string, unknown>
  output?: string
  error?: string
  title?: string
  duration?: number
  /** Tool-reported extras for display: exit_code, blocked, truncated, count. */
  metadata?: Record<string, unknown> | null
}
export interface StepStartPart {
  type: "step-start"
  id: string
  step: number
}
export interface StepFinishPart {
  type: "step-finish"
  id: string
  step: number
  input_tokens: number
  output_tokens: number
  cost: number
  duration: number
}
export interface CompactionPart {
  type: "compaction"
  id: string
  summary?: string
}
export interface SubtaskPart {
  type: "subtask"
  id: string
  agent: string
  description: string
  status: ToolStatus
  output?: string
}
export interface PatchFile {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
}
export interface PatchPart {
  type: "patch"
  id: string
  files: PatchFile[]
  /** Snapshot range this patch covers — lets the UI fetch exactly this step's
   *  line-level diff rather than the session's cumulative one. */
  from_snapshot?: string | null
  to_snapshot?: string | null
}
export interface FilePart {
  type: "file"
  id: string
  path: string
  mime_type?: string
  url?: string
  asset_id?: string
  size?: number
}
export interface AgentSwitchPart {
  type: "agent"
  id: string
  agent: string
}
export interface RetryPart {
  type: "retry"
  id: string
  attempt: number
  reason?: string
}
export interface PlanPart {
  type: "plan"
  id: string
  path: string
  status: PlanStatus
  content: string
}

/** The todo list as it stood at one moment. Appended on every change, so the
 *  order of these against the tool parts is what says which task each call
 *  belongs to — the todo *list* only ever holds the latest state. */
export interface TodoPart {
  type: "todo"
  id: string
  items: TodoItem[]
  source?: "model" | "user"
}

export type MessagePart =
  | TextPart
  | ReasoningPart
  | ToolPart
  | StepStartPart
  | StepFinishPart
  | CompactionPart
  | SubtaskPart
  | PatchPart
  | FilePart
  | AgentSwitchPart
  | RetryPart
  | PlanPart
  | TodoPart

export type MessageRole = "user" | "assistant" | "system"

export type MessageReaction = "up" | "down" | null

export interface MessageWithParts {
  id: string
  session_id: string
  role: MessageRole
  parts: MessagePart[]
  created_at: string
  client_message_id?: string
  agent?: string
  model?: string
  variant?: string | null
  parent_id?: string | null
  finish?: string | null
  summary?: boolean | null
  /** Per-message usage rolled up by the backend (preferred over summing steps). */
  tokens?: TokenUsage | null
  error?: Record<string, unknown> | null
  reaction?: MessageReaction
}

export interface DiffLine {
  type: "add" | "del" | "context"
  content: string
  old_line?: number
  new_line?: number
}
export interface DiffHunk {
  old_start: number
  old_count: number
  new_start: number
  new_count: number
  lines: DiffLine[]
}
export interface DiffEntry {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
  hunks?: DiffHunk[]
}

export type TodoStatus = "pending" | "in_progress" | "completed" | "cancelled"
export interface TodoItem {
  id: string
  subject: string
  description?: string
  status: TodoStatus
  /** Present-tense wording used as the card's heading while this runs. */
  active_form?: string
  priority?: "high" | "medium" | "low"
  /** Who put this on the list — the user's own items can be removed outright. */
  source?: "model" | "user"
  /** ISO time this first became in_progress; the progress bar reads it. */
  started_at?: string | null
}
export interface TodoList {
  items: TodoItem[]
}

export interface ModelInfo {
  id: string
  name: string
  provider?: string
  /** Cap on a single response. */
  max_tokens?: number
  /** Size of the context window, resolved by the backend. */
  context_limit?: number
  /** Whether the model accepts image input. */
  vision?: boolean
}
export interface AgentInfo {
  name: string
  description?: string
  model?: string
}
export interface AppConfig {
  models: ModelInfo[]
  default_model?: string
  default_agent?: string
}

export interface PermissionRequest {
  id: string
  session_id: string
  tool: string
  action?: string
  input?: Record<string, unknown>
  title?: string
  created_at?: string
}
export interface QuestionOption {
  label: string
  description?: string
}
/** One question in a request. The agent may ask up to a handful at once. */
export interface QuestionItem {
  question: string
  header?: string
  options?: QuestionOption[]
  /** Allow picking more than one option. */
  multiple?: boolean
}
export interface QuestionRequest {
  id: string
  session_id: string
  /** The questions asked together. Answered as a set, in this order. */
  questions: QuestionItem[]
  /** The tool call waiting on this, when it came from one. */
  tool?: { messageID?: string; callID?: string } | null
  created_at?: string
}

export interface ContainerInfo {
  id: string
  name: string
  status: string
  image?: string
  created_at?: string
  port?: number | null
}

export interface AuthUser {
  id: string
  username: string
  email?: string
  role: string
}

export interface UserPreferences {
  theme?: string | null
  default_model?: string | null
  default_agent?: string | null
  sidebar_open?: boolean | null
  extra?: Record<string, unknown> | null
}

export interface FileEntry {
  name: string
  path: string
  is_dir: boolean
  size?: number
}
