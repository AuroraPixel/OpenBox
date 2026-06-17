export type SessionStatus = "idle" | "busy" | "finalizing" | "retry" | "error" | "compacting"

export interface Session {
  id: string
  title: string
  agent: string
  model: string
  status: SessionStatus
  created_at: string
  updated_at: string
  slug?: string
  additions?: number
  deletions?: number
  files_changed?: number
  token_usage?: TokenUsage
}

export interface TokenUsage {
  input: number
  output: number
  cache: number
  total: number
  limit: number
  cost: number
  context: number  // Current context window usage (last step's input tokens)
}

export type PlanStatus = "writing" | "ready" | "accepted" | "rejected"

export type PartType =
  | "text"
  | "reasoning"
  | "tool"
  | "step-start"
  | "step-finish"
  | "compaction"
  | "subtask"
  | "patch"
  | "file"
  | "agent"
  | "retry"
  | "plan"

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

export interface ToolPartData {
  type: "tool"
  id: string
  tool: string
  status: ToolStatus
  input?: Record<string, unknown>
  output?: string
  error?: string
  title?: string
  duration?: number
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

export interface PatchPart {
  type: "patch"
  id: string
  files: PatchFile[]
}

export interface PatchFile {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
}

export interface FilePart {
  type: "file"
  id: string
  path: string
  mime_type?: string
  url?: string
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

export interface PlanPartData {
  type: "plan"
  id: string
  path: string
  status: PlanStatus
  content: string
}

export type MessagePart =
  | TextPart
  | ReasoningPart
  | ToolPartData
  | StepStartPart
  | StepFinishPart
  | CompactionPart
  | SubtaskPart
  | PatchPart
  | FilePart
  | AgentSwitchPart
  | RetryPart
  | PlanPartData

export type MessageRole = "user" | "assistant" | "system"

export interface MessageWithParts {
  id: string
  session_id: string
  role: MessageRole
  parts: MessagePart[]
  created_at: string
  client_message_id?: string
  agent?: string
  model?: string
  parent_id?: string | null
  summary?: boolean | null
}

export interface SendOptions {
  agent?: string
  model?: string
  variant?: string
  clientMessageId?: string
}

export interface DiffEntry {
  path: string
  additions: number
  deletions: number
  status: "added" | "modified" | "deleted"
  hunks?: DiffHunk[]
}

export interface DiffHunk {
  old_start: number
  old_count: number
  new_start: number
  new_count: number
  lines: DiffLine[]
}

export interface DiffLine {
  type: "add" | "del" | "context"
  content: string
  old_line?: number
  new_line?: number
}

export interface TodoItem {
  id: string
  subject: string
  description?: string
  status: "pending" | "in_progress" | "completed"
  active_form?: string
}

export interface TodoList {
  items: TodoItem[]
}
