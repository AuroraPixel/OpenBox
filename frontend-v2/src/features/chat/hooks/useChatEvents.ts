// The single WS → store bridge. Mounted once on ChatRoute: every message/part/
// tool event lands in the stream store; todo.updated invalidates the todo query;
// permission/question prompts land in the pending store; a reconnect refetches
// the current session snapshot and the pending lists it may have missed.
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { wsClient } from "@/shared/ws/client"
import { chatKeys } from "../api/keys"
import { useUserId } from "../api/messages"
import { usePendingStore } from "../stores/pending"
import { useStreamStore } from "../stores/stream"

export function useChatEvents(sessionId: string): void {
  const qc = useQueryClient()
  const userId = useUserId()

  useEffect(() => {
    // Ensure the socket is up while a chat is open (idempotent; never disconnects
    // here — the connection is app-global).
    void wsClient.connect()

    const stream = useStreamStore.getState()
    const pending = usePendingStore.getState()
    const offs: Array<() => void> = [
      wsClient.on("message.created", (d) => stream.addMessage(d.sessionId, d.message)),
      wsClient.on("message.updated", (d) => stream.updateMessage(d.sessionId, d.message)),
      wsClient.on("message.text_delta", (d) =>
        stream.appendPartDelta(d.sessionId, d.messageId, d.partId, d.text),
      ),
      wsClient.on("part.created", (d) => stream.addPart(d.sessionId, d.messageId, d.part)),
      wsClient.on("part.updated", (d) => stream.updatePart(d.sessionId, d.messageId, d.part)),
      wsClient.on("part.delta", (d) => stream.appendPartDelta(d.sessionId, d.messageId, d.partId, d.delta)),
      wsClient.on("tool.running", (d) => stream.updateToolStatus(d.sessionId, d.partId, "running", d.data)),
      wsClient.on("tool.completed", (d) =>
        stream.updateToolStatus(d.sessionId, d.partId, "completed", d.data),
      ),
      wsClient.on("tool.error", (d) => stream.updateToolStatus(d.sessionId, d.partId, "error", d.data)),
      wsClient.on("session.status", (d) => stream.setStatus(d.sessionId, d.status)),
      wsClient.on("session.finalizing", (d) => stream.setStatus(d.sessionId, "finalizing")),
      wsClient.on("session.error", (d) => stream.setStatus(d.sessionId, "error")),
      wsClient.on("session.title", () => void qc.invalidateQueries({ queryKey: ["sessions", userId] })),
      wsClient.on("session.updated", () => void qc.invalidateQueries({ queryKey: ["sessions", userId] })),
      wsClient.on(
        "todo.updated",
        (d) => void qc.invalidateQueries({ queryKey: chatKeys.todo(userId, d.sessionId) }),
      ),
      wsClient.on("permission.asked", (d) => pending.addPermission(d)),
      wsClient.on("permission.replied", (d) => pending.removePermission(d.request_id)),
      wsClient.on("question.asked", (d) => pending.addQuestion(d)),
      wsClient.on("question.replied", (d) => pending.removeQuestion(d.request_id)),
      wsClient.on("question.rejected", (d) => pending.removeQuestion(d.request_id)),
      wsClient.on("__connected", () => {
        if (sessionId) void qc.invalidateQueries({ queryKey: chatKeys.messages(userId, sessionId) })
        void qc.invalidateQueries({ queryKey: chatKeys.permissions(userId) })
        void qc.invalidateQueries({ queryKey: chatKeys.questions(userId) })
      }),
    ]
    return () => {
      for (const off of offs) off()
    }
  }, [qc, userId, sessionId])
}
