import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthStore } from "@/shared/api/auth-store"
import { http } from "@/shared/api/http"
import type { MessageWithParts, Session } from "@/shared/types/api"
import { chatKeys } from "./keys"

export function useUserId(): string {
  return useAuthStore((s) => s.user?.id ?? "anonymous")
}

export function useMessagesQuery(sessionId: string) {
  const userId = useUserId()
  return useQuery({
    queryKey: chatKeys.messages(userId, sessionId),
    queryFn: () => http.get<MessageWithParts[]>(`/api/agent/session/${sessionId}/message`),
    enabled: sessionId.length > 0,
  })
}

export interface SendMessageVars {
  text: string
  model?: string
  agent?: string
  variant?: string
  attachments?: string[]
  clientMessageId: string
}

export function useSendMessage(sessionId: string) {
  const qc = useQueryClient()
  const userId = useUserId()
  return useMutation({
    mutationFn: (vars: SendMessageVars) =>
      http.post<{ ok: boolean }>(`/api/agent/session/${sessionId}/prompt_async`, {
        text: vars.text,
        agent: vars.agent,
        model: vars.model,
        variant: vars.variant,
        attachments: vars.attachments?.length ? vars.attachments : undefined,
        client_message_id: vars.clientMessageId,
      }),
    // The backend records the chosen model on the session, so the cached copy
    // is stale the moment a send goes out — and it is what restores the picker
    // when the user comes back to this conversation.
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["session", userId, sessionId] }),
  })
}

export function useAbortSession(sessionId: string) {
  return useMutation({
    mutationFn: () => http.post<{ ok: boolean }>(`/api/agent/session/${sessionId}/abort`),
  })
}

export interface CreateSessionVars {
  projectId?: string
  model?: string
  agent?: string
}

export function useCreateSession() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: CreateSessionVars) =>
      http.post<Session>("/api/agent/session", {
        project_id: vars.projectId,
        model: vars.model,
        agent: vars.agent,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["sessions", userId] }),
  })
}
