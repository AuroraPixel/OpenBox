// Per-message actions backed by the OpenBox agent API: reactions and forking,
// plus the single-session read the meta bar uses to resolve the model name.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { MessageReaction, Session } from "@/shared/types/api"
import { useStreamStore } from "../stores/stream"
import { chatKeys } from "./keys"
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

/** Answer the same prompt again, discarding this assistant turn.
 *
 *  The server deletes the turn, so the local snapshot is stale the moment this
 *  succeeds — the stream store is cleared and refetched rather than merged.
 *  Its merge keeps whichever copy has more parts, which would otherwise
 *  resurrect exactly the messages that were just deleted.
 */
export function useRegenerate(sessionId: string) {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ messageId, model }: { messageId: string; model?: string }) =>
      http.post<{ ok: boolean; from_message: string }>(
        `/api/agent/session/${sessionId}/regenerate/${messageId}`,
        model ? { model } : {},
      ),
    onSuccess: () => {
      useStreamStore.getState().clearMessages(sessionId)
      void qc.invalidateQueries({ queryKey: chatKeys.messages(userId, sessionId) })
      void qc.invalidateQueries({ queryKey: ["session", userId, sessionId] })
    },
  })
}

/** Drop a turn that failed, once the user has moved past it.
 *
 *  Same cache dance as {@link useRegenerate}, and for the same reason: the
 *  server removed messages, so the local snapshot has to be discarded rather
 *  than merged with the new one.
 */
export function useDismissFailedTurn(sessionId: string) {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (messageId: string) =>
      http.delete<{ ok: boolean; removed: number }>(
        `/api/agent/session/${sessionId}/message/${messageId}`,
      ),
    onSuccess: () => {
      useStreamStore.getState().clearMessages(sessionId)
      void qc.invalidateQueries({ queryKey: chatKeys.messages(userId, sessionId) })
    },
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
