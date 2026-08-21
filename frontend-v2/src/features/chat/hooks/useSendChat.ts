import { useCallback } from "react"
import { toast } from "@/shared/ui/Toast"
import { useApiErrorMessage } from "@/shared/hooks/useApiErrorMessage"
import { useSendMessage, type SendMessageVars } from "../api/messages"
import { makeClientId, optimisticUserMessage } from "../lib/message"
import { useStreamStore } from "../stores/stream"

export interface SendOpts {
  model?: string
  agent?: string
  attachments?: string[]
}

/** Send a prompt in an existing session: optimistic echo + busy status + POST. */
export function useSendChat(sessionId: string): (text: string, opts?: SendOpts) => void {
  const send = useSendMessage(sessionId)
  const errorMessage = useApiErrorMessage()
  const { mutate } = send

  return useCallback(
    (text, opts) => {
      const trimmed = text.trim()
      if (!trimmed) return
      const clientMessageId = makeClientId()
      const store = useStreamStore.getState()
      store.addMessage(sessionId, optimisticUserMessage(sessionId, trimmed, clientMessageId))
      store.setStatus(sessionId, "busy")
      const vars: SendMessageVars = { text: trimmed, model: opts?.model, agent: opts?.agent, attachments: opts?.attachments, clientMessageId }
      mutate(vars, {
        onError: (err) => {
          useStreamStore.getState().setStatus(sessionId, "idle")
          toast("error", errorMessage(err))
        },
      })
    },
    [sessionId, mutate, errorMessage],
  )
}
