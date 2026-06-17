/**
 * WebSocket event subscriptions — replaces useSSE.
 * Same event names, same store actions, but using wsClient instead of sseClient.
 */
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { wsClient } from "@/services/ws"
import { api } from "@/services/api"
import { useSessionStore } from "@/stores/session"
import { usePermissionStore } from "@/stores/permission"
import { useQuestionStore } from "@/stores/question"
import { useUIStore } from "@/stores/ui"
import { useToast } from "@/components/ui/Toast"
import type {
  MessageWithParts, MessagePart, SessionStatus, TokenUsage,
  PermissionRequest, QuestionRequest,
} from "@/types"

export function useWS() {
  const { addToast } = useToast()
  const queryClient = useQueryClient()

  useEffect(() => {
    const unsubscribers: Array<() => void> = []

    // Connection status — on reconnect, refresh state that may have been missed
    unsubscribers.push(wsClient.on("__connected", () => {
      useUIStore.getState().setWsConnected(true)
      // Refresh pending permissions & questions
      api.listPendingPermissions().then((items) => {
        const store = usePermissionStore.getState()
        for (const item of items) store.addPending(item)
      }).catch(() => {})
      api.listPendingQuestions().then((items) => {
        const store = useQuestionStore.getState()
        for (const item of items) store.addPending(item)
      }).catch(() => {})
      // Refresh messages for current session (may have missed events during disconnect)
      const currentSession = useSessionStore.getState().currentSessionId
      if (currentSession) {
        api.getMessages(currentSession).then((msgs) => {
          const store = useSessionStore.getState()
          store.setMessages(currentSession, msgs)
        }).catch(() => {})
      }
    }))
    unsubscribers.push(wsClient.on("__disconnected", () => {
      useUIStore.getState().setWsConnected(false)
    }))

    // Session status
    unsubscribers.push(wsClient.on("session.status", (data: unknown) => {
      const d = data as { sessionId: string; status: SessionStatus }
      useSessionStore.getState().updateSessionStatus(d.sessionId, d.status)
    }))
    unsubscribers.push(wsClient.on("session.finalizing", (data: unknown) => {
      const d = data as { sessionId: string }
      useSessionStore.getState().updateSessionStatus(d.sessionId, "finalizing")
    }))

    unsubscribers.push(wsClient.on("session.title", (data: unknown) => {
      const d = data as { sessionId: string; title: string }
      useSessionStore.getState().updateSessionTitle(d.sessionId, d.title)
    }))

    unsubscribers.push(wsClient.on("session.updated", (data: unknown) => {
      const d = data as { sessionId: string; token_usage?: TokenUsage; agent?: string; planUpdated?: boolean }
      if (d.token_usage) {
        useSessionStore.getState().updateSessionTokens(d.sessionId, d.token_usage)
      }
      if (d.agent) {
        useSessionStore.getState().updateSessionAgent(d.sessionId, d.agent)
      }
      if (d.planUpdated) {
        useSessionStore.getState().notifyPlanUpdated(d.sessionId)
      }
    }))

    unsubscribers.push(wsClient.on("session.error", (data: unknown) => {
      const d = data as { sessionId: string; error: { message: string } }
      useSessionStore.getState().updateSessionStatus(d.sessionId, "error")
      addToast("error", d.error?.message || "Session error")
    }))

    unsubscribers.push(wsClient.on("session.diff", (data: unknown) => {
      const d = data as { sessionId: string }
      useSessionStore.getState().notifyDiffUpdated(d.sessionId)
    }))

    // Messages
    unsubscribers.push(wsClient.on("message.created", (data: unknown) => {
      const d = data as { sessionId: string; message: MessageWithParts }
      useSessionStore.getState().addMessage(d.sessionId, d.message)
    }))
    unsubscribers.push(wsClient.on("message.updated", (data: unknown) => {
      const d = data as { sessionId: string; message: MessageWithParts }
      useSessionStore.getState().updateMessage(d.sessionId, d.message)
    }))
    unsubscribers.push(wsClient.on("message.text_delta", (data: unknown) => {
      const d = data as { sessionId: string; messageId: string; partId: string; text: string }
      useSessionStore.getState().appendTextDelta(d.sessionId, d.messageId, d.partId, d.text)
    }))

    // Parts
    unsubscribers.push(wsClient.on("part.created", (data: unknown) => {
      const d = data as { sessionId: string; messageId: string; part: MessagePart }
      useSessionStore.getState().addPart(d.sessionId, d.messageId, d.part)
    }))
    unsubscribers.push(wsClient.on("part.updated", (data: unknown) => {
      const d = data as { sessionId: string; messageId: string; part: MessagePart }
      useSessionStore.getState().updatePart(d.sessionId, d.messageId, d.part)
    }))
    unsubscribers.push(wsClient.on("part.delta", (data: unknown) => {
      const d = data as { sessionId: string; messageId: string; partId: string; delta: string }
      useSessionStore.getState().appendPartDelta(d.sessionId, d.messageId, d.partId, d.delta)
    }))

    // Tools
    unsubscribers.push(wsClient.on("tool.running", (data: unknown) => {
      const d = data as { sessionId: string; partId: string; tool: string; input: Record<string, unknown> }
      useSessionStore.getState().updateToolStatus(d.sessionId, d.partId, "running", d)
    }))
    unsubscribers.push(wsClient.on("tool.completed", (data: unknown) => {
      const d = data as { sessionId: string; partId: string; output: string; title?: string }
      useSessionStore.getState().updateToolStatus(d.sessionId, d.partId, "completed", d)
    }))
    unsubscribers.push(wsClient.on("tool.error", (data: unknown) => {
      const d = data as { sessionId: string; partId: string; error: string }
      useSessionStore.getState().updateToolStatus(d.sessionId, d.partId, "error", d)
    }))

    // Permission
    unsubscribers.push(wsClient.on("permission.asked", (data: unknown) => {
      usePermissionStore.getState().addPending(data as PermissionRequest)
    }))
    unsubscribers.push(wsClient.on("permission.replied", (data: unknown) => {
      const d = data as { id: string }
      usePermissionStore.getState().removePending(d.id)
    }))

    // Question
    unsubscribers.push(wsClient.on("question.asked", (data: unknown) => {
      useQuestionStore.getState().addPending(data as QuestionRequest)
    }))
    unsubscribers.push(wsClient.on("question.replied", (data: unknown) => {
      const d = data as { id: string }
      useQuestionStore.getState().removePending(d.id)
    }))
    unsubscribers.push(wsClient.on("question.rejected", (data: unknown) => {
      const d = data as { id: string }
      useQuestionStore.getState().removePending(d.id)
    }))

    // Todo
    unsubscribers.push(wsClient.on("todo.updated", (data: unknown) => {
      const d = data as { sessionId: string }
      useSessionStore.getState().notifyTodoUpdated(d.sessionId)
    }))

    // Compaction
    unsubscribers.push(wsClient.on("session.compaction.start", (data: unknown) => {
      const d = data as { sessionId: string }
      useSessionStore.getState().updateSessionStatus(d.sessionId, "compacting")
    }))
    unsubscribers.push(wsClient.on("session.compaction.complete", (data: unknown) => {
      const d = data as { sessionId: string }
      useSessionStore.getState().updateSessionStatus(d.sessionId, "idle")
    }))

    // F10: Toast notifications from backend
    unsubscribers.push(wsClient.on("toast", (data: unknown) => {
      const d = data as { level: "info" | "success" | "warning" | "error"; message: string }
      if (d.level && d.message) {
        addToast(d.level, d.message)
      }
    }))

    // Build progress (replaces EventSource-based build)
    unsubscribers.push(wsClient.on("build.progress", (_data: unknown) => {
      // Can be consumed by components that need build status
    }))
    unsubscribers.push(wsClient.on("build.complete", (_data: unknown) => {
      addToast("success", "Sandbox image built successfully")
    }))
    unsubscribers.push(wsClient.on("build.error", (data: unknown) => {
      const d = data as { message: string }
      addToast("error", d.message || "Build failed")
    }))

    // Container status changes
    unsubscribers.push(wsClient.on("container.status", () => {
      queryClient.invalidateQueries({ queryKey: ["containers"] }).catch(() => {})
      queryClient.invalidateQueries({ queryKey: ["containers-mention"] }).catch(() => {})
    }))

    // Dev-browser status changes
    unsubscribers.push(wsClient.on("devbrowser.status", () => {
      queryClient.invalidateQueries({ queryKey: ["dev-browser-status"] }).catch(() => {})
    }))

    // Cron job events
    const cronEvents = ["cron.job.created", "cron.job.updated", "cron.job.completed", "cron.job.failed", "cron.job.injected"]
    for (const evt of cronEvents) {
      unsubscribers.push(wsClient.on(evt, () => {
        queryClient.invalidateQueries({ queryKey: ["cron-jobs"] }).catch(() => {})
        queryClient.invalidateQueries({ queryKey: ["cron-runs"] }).catch(() => {})
      }))
    }

    // Connect
    wsClient.connect()

    return () => {
      unsubscribers.forEach((unsub) => unsub())
      wsClient.disconnect()
    }
  }, [addToast, queryClient])
}
