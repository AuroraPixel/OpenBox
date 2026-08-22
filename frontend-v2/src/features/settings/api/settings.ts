// Settings data hooks. Components never fetch directly (ENGINEERING_SPEC §7).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import { useAuthStore } from "@/shared/api/auth-store"
import type { Session, UserPreferences } from "@/shared/types/api"
import { settingsKeys } from "./keys"

export interface ConfigModel {
  id: string
  name: string
  provider?: string
  max_tokens?: number
}
export interface AgentConfig {
  models: ConfigModel[]
  default_model?: string
  default_agent?: string
}
export interface AgentSummary {
  name: string
  description?: string
  model?: string
  /** "primary" | "subagent" | "all". The list only ever serves agents a
   *  person may pick, so a subagent never appears here. */
  mode?: string
  /** Accent colour the agent asked for, if any. */
  color?: string | null
}
export interface SkillSummary {
  name?: string
  description?: string
}
export interface McpServer {
  name?: string
  status?: string
  connected?: boolean
}

function useUserId(): string {
  return useAuthStore((s) => s.user?.id ?? "anonymous")
}

export function useAgentConfig() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.config(userId),
    queryFn: () => http.get<AgentConfig>("/api/agent/config"),
    staleTime: 60_000,
  })
}

export function useAgents() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.agents(userId),
    queryFn: () => http.get<AgentSummary[]>("/api/agent/agent"),
    staleTime: 60_000,
  })
}

export function useSkills() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.skills(userId),
    queryFn: () => http.get<SkillSummary[]>("/api/agent/skill"),
    staleTime: 60_000,
  })
}

export function useMcpServers() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.mcp(userId),
    queryFn: () => http.get<McpServer[]>("/api/agent/mcp"),
    staleTime: 60_000,
  })
}

export function usePreferences() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.prefs(userId),
    queryFn: () => http.get<UserPreferences>("/api/auth/me/preferences"),
  })
}

export function useUpdatePreferences() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: Partial<Pick<UserPreferences, "default_model" | "default_agent">>) =>
      http.put<UserPreferences>("/api/auth/me/preferences", patch),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.prefs(userId) }),
  })
}

export function useUsageSessions() {
  const userId = useUserId()
  return useQuery({
    queryKey: settingsKeys.sessions(userId),
    queryFn: () => http.get<Session[]>("/api/agent/session"),
    staleTime: 30_000,
  })
}
