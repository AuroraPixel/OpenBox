import type {
  ContainerInfo, ContainerListResponse, CreateContainerRequest, SystemInfo,
  Session, MessageWithParts, DiffEntry, TodoList,
  AgentConfig, SkillInfo, McpServer, CommandInfo, AppConfig,
  PermissionRequest, QuestionRequest,
} from "@/types"

const BASE_URL = import.meta.env.VITE_API_URL || ""

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Inject auth header if available
  const { useAuthStore, refreshAccessToken } = await import("@/stores/auth")
  const token = useAuthStore.getState().accessToken

  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const mergedHeaders = { ...headers, ...(options?.headers as Record<string, string> || {}) }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: mergedHeaders,
    credentials: "include",
  })

  // Auto-refresh on 401
  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      headers["Authorization"] = `Bearer ${newToken}`
      const retry = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers: { ...headers, ...(options?.headers as Record<string, string> || {}) },
        credentials: "include",
      })
      if (!retry.ok) {
        const err = await retry.json().catch(() => ({ detail: retry.statusText }))
        throw new Error(err.detail || "Request failed")
      }
      return retry.json()
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || "Request failed")
  }
  return res.json()
}

const realApi = {
  // ===== Sandbox Health Check =====
  getSandboxStatus: () =>
    request<{
      available: boolean
      container_id?: string
      container_name?: string
      status?: string
      containers?: Array<{ id: string; name: string; status: string; port: number | null }>
    }>("/api/agent/sandbox/status"),

  // ===== Existing: Container Management =====
  checkSandboxImage: () =>
    request<{ exists: boolean; image: string }>("/api/containers/sandbox-image/status"),
  buildSandboxImage: async () => {
    const { wsClient } = await import("@/services/ws")
    wsClient.startBuild()
  },
  createContainer: (data: CreateContainerRequest) =>
    request<ContainerInfo>("/api/containers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listContainers: () => request<ContainerListResponse>("/api/containers"),
  getContainer: (id: string) => request<ContainerInfo>(`/api/containers/${id}`),
  deleteContainer: (id: string) =>
    request<void>(`/api/containers/${id}`, { method: "DELETE" }),
  stopContainer: (id: string) =>
    request<void>(`/api/containers/${id}/stop`, { method: "POST" }),
  startContainer: (id: string) =>
    request<void>(`/api/containers/${id}/start`, { method: "POST" }),
  getSystemInfo: (containerId: string) =>
    request<SystemInfo>(`/api/containers/${containerId}/files/system_info`),
  listFiles: (containerId: string, path: string) =>
    request<{ files: Array<{ name: string; is_dir: boolean; size: number | null; modified: string | null }> }>(
      `/api/containers/${containerId}/files/list`,
      { method: "POST", body: JSON.stringify({ path }) },
    ),
  getListeningPorts: (containerId: string) =>
    request<{ ports: Array<{ port: number; pid: number | null; process: string; command: string }> }>(
      `/api/containers/${containerId}/ports`
    ),
  getPreviewToken: (containerId: string, port: number) =>
    request<{ token: string; url: string }>(
      `/api/containers/${containerId}/preview-token?port=${port}`,
      { method: "POST" },
    ),
  getTerminalWsUrl: async (containerId: string) => {
    const wsBase = (BASE_URL || window.location.origin).replace(/^http/, "ws")
    // Get ticket for WS auth
    try {
      const { useAuthStore, refreshAccessToken } = await import("@/stores/auth")
      let token = useAuthStore.getState().accessToken
      if (!token) {
        token = await refreshAccessToken()
      }
      if (token) {
        const resp = await fetch(`${BASE_URL}/api/auth/ticket`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) {
          const { ticket } = await resp.json()
          return `${wsBase}/ws/terminal/${containerId}?ticket=${ticket}`
        }
      }
    } catch {}
    // Fallback: no ticket (single-user mode)
    return `${wsBase}/ws/terminal/${containerId}`
  },

  // ===== Dev Browser =====
  startDevBrowser: (containerId: string) =>
    request<{ status: string; pid?: number }>(`/api/containers/${containerId}/dev-browser/start`, {
      method: "POST",
    }),
  stopDevBrowser: (containerId: string) =>
    request<{ status: string }>(`/api/containers/${containerId}/dev-browser/stop`, {
      method: "POST",
    }),
  getDevBrowserStatus: (containerId: string) =>
    request<{ status: string; pid?: number; extensionConnected: boolean }>(
      `/api/containers/${containerId}/dev-browser/status`
    ),
  getDevBrowserLinkInfo: () =>
    request<{ has_link: boolean; connected?: boolean; client_id?: string }>(
      `/api/containers/dev-browser/link-info`
    ),
  getDevBrowserWsUrl: async (containerId: string) => {
    const wsBase = (BASE_URL || window.location.origin).replace(/^http/, "ws")
    try {
      const { useAuthStore, refreshAccessToken } = await import("@/stores/auth")
      let token = useAuthStore.getState().accessToken
      if (!token) {
        token = await refreshAccessToken()
      }
      if (token) {
        const resp = await fetch(`${BASE_URL}/api/auth/ticket`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) {
          const { ticket } = await resp.json()
          return `${wsBase}/ws/dev-browser/${containerId}?ticket=${ticket}`
        }
      }
    } catch {}
    return `${wsBase}/ws/dev-browser/${containerId}`
  },

  // ===== Cron Jobs =====
  getCronStatus: () =>
    request<{ running: boolean; total_jobs: number; enabled_jobs: number; running_jobs: number }>("/api/cron/status"),
  listCronJobs: (sessionId?: string) => {
    const params = sessionId ? `?session_id=${sessionId}` : ""
    return request<Array<Record<string, unknown>>>(`/api/cron/jobs${params}`)
  },
  createCronJob: (data: Record<string, unknown>) =>
    request<{ id: string; next_run_at: string | null }>("/api/cron/jobs", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateCronJob: (jobId: string, data: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/api/cron/jobs/${jobId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteCronJob: (jobId: string) =>
    request<{ ok: boolean }>(`/api/cron/jobs/${jobId}`, { method: "DELETE" }),
  runCronJob: (jobId: string) =>
    request<{ ok: boolean; status?: string }>(`/api/cron/jobs/${jobId}/run`, { method: "POST" }),
  getCronJob: (jobId: string) =>
    request<Record<string, unknown>>(`/api/cron/jobs/${jobId}`),
  listCronRuns: (jobId: string, limit = 20) =>
    request<Array<Record<string, unknown>>>(`/api/cron/jobs/${jobId}/runs?limit=${limit}`),

  // ===== New: OpenAgent Session =====
  createSession: (options?: { model?: string; agent?: string }) =>
    request<Session>("/api/agent/session", {
      method: "POST",
      body: options ? JSON.stringify(options) : undefined,
    }),
  listSessions: () =>
    request<Session[]>("/api/agent/session"),
  getSession: (id: string) =>
    request<Session>(`/api/agent/session/${id}`),
  deleteSession: (id: string) =>
    request<void>(`/api/agent/session/${id}`, { method: "DELETE" }),
  updateSession: (id: string, data: Partial<Session>) =>
    request<Session>(`/api/agent/session/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // ===== New: Session Sandbox =====
  getSessionSandbox: (sessionId: string) =>
    request<{ available: boolean; container_id?: string; port?: number; project_id?: string }>(
      `/api/agent/session/${sessionId}/sandbox`
    ),

  // ===== New: Messages =====
  getMessages: (sessionId: string) =>
    request<MessageWithParts[]>(`/api/agent/session/${sessionId}/message`),
  sendMessage: (sessionId: string, text: string) =>
    request<MessageWithParts>(`/api/agent/session/${sessionId}/message`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  sendMessageAsync: (
    sessionId: string,
    text: string,
    options?: { agent?: string; model?: string; variant?: string; clientMessageId?: string },
  ) => {
    const { clientMessageId, ...rest } = options || {}
    return request<{ ok: boolean }>(`/api/agent/session/${sessionId}/prompt_async`, {
      method: "POST",
      body: JSON.stringify({
        text,
        ...rest,
        client_message_id: clientMessageId,
      }),
    })
  },
  abortSession: (sessionId: string) =>
    request<void>(`/api/agent/session/${sessionId}/abort`, { method: "POST" }),

  // ===== New: Compaction =====
  summarize: (sessionId: string) =>
    request<void>(`/api/agent/session/${sessionId}/summarize`, { method: "POST" }),

  // ===== New: Revert =====
  revert: (sessionId: string, messageId: string) =>
    request<void>(`/api/agent/session/${sessionId}/revert/${messageId}`, { method: "POST" }),
  unrevert: (sessionId: string) =>
    request<void>(`/api/agent/session/${sessionId}/unrevert`, { method: "POST" }),

  // ===== New: Command =====
  executeCommand: (sessionId: string, command: string, args?: string) =>
    request<void>(`/api/agent/session/${sessionId}/command`, {
      method: "POST",
      body: JSON.stringify({ command, arguments: args }),
    }),

  // ===== New: Todo =====
  getTodo: (sessionId: string) =>
    request<TodoList>(`/api/agent/session/${sessionId}/todo`),

  // ===== New: Plan =====
  getPlan: (sessionId: string) =>
    request<{ content: string | null; path: string }>(`/api/agent/session/${sessionId}/plan`),
  updatePlan: (sessionId: string, content: string) =>
    request<{ ok: boolean }>(`/api/agent/session/${sessionId}/plan`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  acceptPlan: (sessionId: string) =>
    request<{ ok: boolean }>(`/api/agent/session/${sessionId}/plan/accept`, { method: "POST" }),
  rejectPlan: (sessionId: string) =>
    request<{ ok: boolean }>(`/api/agent/session/${sessionId}/plan/reject`, { method: "POST" }),

  // ===== New: Diff =====
  getSessionDiff: (sessionId: string) =>
    request<DiffEntry[]>(`/api/agent/session/${sessionId}/diff?full=true`),

  // ===== New: Permission & Question =====
  listPendingPermissions: () =>
    request<PermissionRequest[]>("/api/agent/permission"),
  replyPermission: (id: string, action: string, message?: string) =>
    request<void>(`/api/agent/permission/${id}`, {
      method: "POST",
      body: JSON.stringify({ action, message }),
    }),
  listPendingQuestions: () =>
    request<QuestionRequest[]>("/api/agent/question"),
  replyQuestion: (id: string, answers: string[][]) =>
    request<void>(`/api/agent/question/${id}`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  rejectQuestion: (id: string) =>
    request<void>(`/api/agent/question/${id}/reject`, { method: "POST" }),

  // ===== New: Config & Metadata =====
  getConfig: () =>
    request<AppConfig>("/api/agent/config"),
  listAgents: () =>
    request<AgentConfig[]>("/api/agent/agent"),
  listSkills: () =>
    request<SkillInfo[]>("/api/agent/skill"),
  getSkill: (name: string) =>
    request<SkillInfo>(`/api/agent/skill/${name}`),
  installSkill: (data: { url?: string; content?: string; name?: string }) =>
    request<SkillInfo>("/api/agent/skill/install", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  uninstallSkill: (name: string) =>
    request<void>(`/api/agent/skill/${name}`, { method: "DELETE" }),
  uploadSkillArchive: async (file: File, name?: string) => {
    const { useAuthStore, refreshAccessToken } = await import("@/stores/auth")
    let token = useAuthStore.getState().accessToken
    const formData = new FormData()
    formData.append("file", file)
    if (name) formData.append("name", name)
    const headers: Record<string, string> = {}
    if (token) headers["Authorization"] = `Bearer ${token}`
    const resp = await fetch(`${BASE_URL}/api/agent/skill/upload`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    })
    if (resp.status === 401 && token) {
      const newToken = await refreshAccessToken()
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`
        const retry = await fetch(`${BASE_URL}/api/agent/skill/upload`, { method: "POST", headers, body: formData, credentials: "include" })
        if (!retry.ok) { const err = await retry.json().catch(() => ({ detail: retry.statusText })); throw new Error(err.detail || "Upload failed") }
        return retry.json()
      }
    }
    if (!resp.ok) { const err = await resp.json().catch(() => ({ detail: resp.statusText })); throw new Error(err.detail || "Upload failed") }
    return resp.json()
  },
  listCommands: () =>
    request<CommandInfo[]>("/api/agent/command"),
  getMcpStatus: () =>
    request<McpServer[]>("/api/agent/mcp"),
  addMcpServer: (data: { name: string; type: string; command?: string; args?: string[]; url?: string; env?: Record<string, string>; headers?: Record<string, string>; timeout?: number }) =>
    request<void>("/api/agent/mcp", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  removeMcpServer: (name: string) =>
    request<void>(`/api/agent/mcp/${name}`, { method: "DELETE" }),
  connectMcp: (name: string) =>
    request<void>(`/api/agent/mcp/${name}/connect`, { method: "POST" }),
  disconnectMcp: (name: string) =>
    request<void>(`/api/agent/mcp/${name}/disconnect`, { method: "POST" }),
  refreshMcp: (name: string) =>
    request<{ tools: number; resources: number; prompts: number; tools_changed: boolean }>(
      `/api/agent/mcp/${name}/refresh`, { method: "POST" }
    ),
  listMcpResources: () =>
    request<Array<{ uri: string; name: string; description: string; mimeType: string; server: string }>>(
      "/api/agent/mcp/resources"
    ),
  readMcpResource: (server: string, uri: string) =>
    request<{ contents: Array<{ uri: string; text?: string; blob?: string; mimeType?: string }> }>(
      "/api/agent/mcp/resources/read", { method: "POST", body: JSON.stringify({ server, uri }) }
    ),
  listMcpPrompts: () =>
    request<Array<{ name: string; description: string; arguments: Array<{ name: string; description: string; required: boolean }>; server: string }>>(
      "/api/agent/mcp/prompts"
    ),
  getMcpPrompt: (server: string, name: string, args?: Record<string, string>) =>
    request<{ messages: Array<{ role: string; content: Array<{ type: string; text?: string }> }> }>(
      "/api/agent/mcp/prompts/get", { method: "POST", body: JSON.stringify({ server, name, arguments: args }) }
    ),

  // F4: Prompt history
  getPromptHistory: (limit = 100) =>
    request<Array<{ id: string; content: string; created_at: string }>>(
      `/api/agent/prompt-history?limit=${limit}`
    ),
  addPromptHistory: (content: string) =>
    request<{ ok: boolean }>("/api/agent/prompt-history", {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  // F7: Session fork
  forkSession: (sessionId: string, messageId?: string) =>
    request<Session>(`/api/agent/session/${sessionId}/fork`, {
      method: "POST",
      body: JSON.stringify({ message_id: messageId }),
    }),

  // F8: MCP OAuth
  startMcpOAuth: (serverName: string) =>
    request<{ authorize_url: string; state: string }>("/api/agent/mcp/oauth/start", {
      method: "POST",
      body: JSON.stringify({ server_name: serverName }),
    }),
}

export const api = realApi
