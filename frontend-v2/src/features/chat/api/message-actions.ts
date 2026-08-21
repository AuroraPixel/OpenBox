// Per-message actions backed by the OpenBox agent API: reactions and forking,
// plus the single-session read the meta bar uses to resolve the model name.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { MessageReaction, Session } from "@/shared/types/api"
import { useUserId } from "./messages"

/** One session by id. Shares the ["session", userId, id] cache with the
 *  workspace layer, so both read the same fetched entry. */
export function useSessionQuery(sessionId: string) {
  const userId = useUserId()
  return useQuery({
    queryKey: ["session", userId, sessionId],
    queryFn: () => http.get<Session>(`/api/agent/session/${sessionId}`),
    enabled: sessionId.length > 0,
    staleTime: 30_000,
  })
}

interface ReactionVars {
  messageId: string
  reaction: MessageReaction
}

/** POST a thumbs up/down (or `null` to clear) for one assistant message. */
export function useSetReaction(sessionId: string) {
  return useMutation({
    mutationFn: ({ messageId, reaction }: ReactionVars) =>
      http.post<{ ok: boolean; reaction: MessageReaction }>(
        `/api/agent/session/${sessionId}/message/${messageId}/reaction`,
        { reaction },
      ),
  })
}

/** Fork the conversation at a message into a fresh session. */
export function useForkMessage(sessionId: string) {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (messageId: string) =>
      http.post<Session>(`/api/agent/session/${sessionId}/fork`, { message_id: messageId }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["sessions", userId] }),
  })
}
