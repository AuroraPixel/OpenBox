export type ContainerStatus = "creating" | "running" | "stopped" | "error"

export interface ContainerInfo {
  id: string
  name: string
  status: ContainerStatus
  image: string
  created_at: string
  port: number | null
  api_key: string | null
}

export interface ContainerListResponse {
  containers: ContainerInfo[]
  total: number
}

export interface CreateContainerRequest {
  name: string
  image?: string
}

export interface WSMessage {
  type: "input" | "output" | "error" | "heartbeat"
  data?: string
  exit_code?: number
}

export interface FileEntry {
  name: string
  is_dir: boolean
  size: number | null
  modified: string | null
}

export interface SystemInfo {
  cpu: { percent: number; count: number }
  memory: { total: number; used: number; percent: number }
  disk: { total: number; used: number; free: number; percent: number }
}

// Binary frame protocol prefixes
export const TERMINAL_MSG_DATA = 0x00
export const TERMINAL_MSG_RESIZE = 0x01

// Re-export new types
export type {
  Session, SessionStatus, TokenUsage,
  MessageWithParts, MessagePart, MessageRole, SendOptions,
  TextPart, ReasoningPart, ToolPartData, StepStartPart, StepFinishPart,
  CompactionPart, SubtaskPart, PatchPart, PatchFile, FilePart,
  AgentSwitchPart, RetryPart, ToolStatus, PlanPartData, PlanStatus,
  DiffEntry, DiffHunk, DiffLine,
  TodoItem, TodoList,
} from "./session"

export type {
  AgentConfig, ModelInfo, SkillInfo, McpServer, McpTool, McpResource, McpPrompt, CommandInfo, AppConfig,
} from "./agent"

export type {
  PermissionRequest, PermissionAction, PermissionReplied,
} from "./permission"

export type {
  QuestionOption, Question, QuestionRequest, QuestionAnswer,
} from "./question"
