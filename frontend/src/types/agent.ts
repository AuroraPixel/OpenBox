export interface AgentConfig {
  name: string
  description: string
  model: string
  temperature: number
  tools: string[]
  system_prompt?: string
}

export interface ModelInfo {
  id: string
  name: string
  provider: string
  max_tokens: number
  variants?: string[]
}

export interface SkillInfo {
  name: string
  description: string
  source: "global" | "project" | "remote" | "container"
  content?: string
  files?: string[]
}

export interface McpServer {
  name: string
  type: "stdio" | "remote"
  status: "connected" | "disconnected" | "error"
  tools: McpTool[]
  resources?: McpResource[]
  prompts?: McpPrompt[]
  error?: string
  command?: string
  args?: string[]
  url?: string
}

export interface McpTool {
  name: string
  description: string
  input_schema?: Record<string, unknown>
  server?: string
}

export interface McpResource {
  uri: string
  name: string
  description: string
  mimeType: string
  server: string
}

export interface McpPrompt {
  name: string
  description: string
  arguments: { name: string; description: string; required: boolean }[]
  server: string
}

export interface CommandInfo {
  name: string
  description: string
  arguments?: string
}

export interface AppConfig {
  models: ModelInfo[]
  default_model: string
  default_agent: string
}
