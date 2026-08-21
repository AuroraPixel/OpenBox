import { useCallback } from "react"
import { http } from "@/shared/api/http"
import { toast } from "@/shared/ui/Toast"
import { useApiErrorMessage } from "@/shared/hooks/useApiErrorMessage"
import { useCreateSession } from "../api/messages"
import { makeClientId, optimisticUserMessage } from "../lib/message"
import { useStreamStore } from "../stores/stream"

export interface StartOpts {
  model?: string
  agent?: string
  projectId?: string
  attachments?: string[]
}

/**
 * From the empty state: create a session, seed the first message, hand the new
 * id to `onSession` (the route navigates), then send the prompt. Navigation is
 * injected so the feature never depends on the app router.
 */
export function useStartChat(
  onSession: (sessionId: string) => void,
): (text: string, opts?: StartOpts) => Promise<void> {
  const create = useCreateSession()
  const errorMessage = useApiErrorMessage()

  return useCallback(
    async (text, opts) => {
      const trimmed = text.trim()
      if (!trimmed) return
      let sessionId: string
      try {
        const session = await create.mutateAsync({
          projectId: opts?.projectId,
          model: opts?.model,
          agent: opts?.agent,
        })
        sessionId = session.id
      } catch (err) {
        toast("error", errorMessage(err))
        return
      }

      const clientMessageId = makeClientId()
      const store = useStreamStore.getState()
      store.addMessage(sessionId, optimisticUserMessage(sessionId, trimmed, clientMessageId))
      store.setStatus(sessionId, "busy")
      onSession(sessionId)

      try {
        await http.post(`/api/agent/session/${sessionId}/prompt_async`, {
          text: trimmed,
          model: opts?.model,
          agent: opts?.agent,
          attachments: opts?.attachments?.length ? opts.attachments : undefined,
          client_message_id: clientMessageId,
        })
      } catch (err) {
        useStreamStore.getState().setStatus(sessionId, "idle")
        toast("error", errorMessage(err))
      }
    },
    [create, onSession, errorMessage],
  )
}
