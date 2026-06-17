import { useCallback, useEffect, useMemo, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { useToast } from "@/components/ui/Toast"
import { useSessionStore } from "@/stores/session"
import { usePermissionStore } from "@/stores/permission"
import { useQuestionStore } from "@/stores/question"
import { MessageList } from "./MessageList"
import { InputBar } from "./InputBar"
import { PermissionDialog } from "@/components/permission/PermissionDialog"
import { QuestionCard } from "@/components/question/QuestionCard"
import { PlanBanner } from "@/components/plan/PlanBanner"
import { BrowserUseBanner } from "@/components/browser/BrowserUseBanner"
import { useUIStore } from "@/stores/ui"
import { useAuthStore } from "@/stores/auth"
import { api } from "@/services/api"
import type { MessageWithParts } from "@/types"

const EMPTY_MESSAGES: import("@/types").MessageWithParts[] = []

interface ChatViewProps {
  sessionId: string
  onNavigate: (path: string) => void
}

export function ChatView({ sessionId, onNavigate }: ChatViewProps) {
  const { addToast } = useToast()
  const resolvedSessionId = useSessionStore((s) => s.resolveSessionId(sessionId))
  const messagesFromStore = useSessionStore((s) => s.messages.get(resolvedSessionId))
  const messages = messagesFromStore ?? EMPTY_MESSAGES
  const setMessages = useSessionStore((s) => s.setMessages)
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === resolvedSessionId))
  const allPermissions = usePermissionStore((s) => s.pending)
  const allQuestions = useQuestionStore((s) => s.pending)
  const pendingPermissions = useMemo(
    () => allPermissions.filter((p) => p.session_id === resolvedSessionId),
    [allPermissions, resolvedSessionId],
  )
  const pendingQuestions = useMemo(
    () => allQuestions.filter((q) => q.session_id === resolvedSessionId),
    [allQuestions, resolvedSessionId],
  )

  const addSession = useSessionStore((s) => s.addSession)
  const addMessage = useSessionStore((s) => s.addMessage)
  const authUserId = useAuthStore((s) => s.user?.id || null)

  const isBusy = session?.status === "busy" || session?.status === "finalizing"
  const isPlanMode = session?.agent === "plan"

  useEffect(() => {
    if (sessionId.startsWith("mock-") && resolvedSessionId !== sessionId && !resolvedSessionId.startsWith("mock-")) {
      onNavigate(`/session/${resolvedSessionId}`)
    }
  }, [sessionId, resolvedSessionId, onNavigate])

  // Compute step progress text from latest assistant message
  const busyStatusText = useMemo(() => {
    if (!isBusy || messages.length === 0) return undefined
    if (session?.status === "finalizing") return "Finalizing..."
    const lastMsg = messages[messages.length - 1]
    if (lastMsg.role !== "assistant") return undefined
    const parts = lastMsg.parts
    // Find current step number
    let stepNum = 0
    let currentTool = ""
    for (const p of parts) {
      if (p.type === "step-start") stepNum = (p as { step: number }).step
      if (p.type === "tool" && ((p as { status?: string }).status === "running" || (p as { status?: string }).status === "pending")) {
        currentTool = (p as { tool?: string }).tool || "tool"
      }
    }
    if (currentTool) return `Step ${stepNum || 1} — Running ${currentTool}`
    if (stepNum) return `Step ${stepNum} — Thinking...`
    return undefined
  }, [isBusy, messages, session?.status])

  // Fetch session details from API if not in store yet
  const { data: fetchedSession } = useQuery({
    queryKey: ["session", authUserId, resolvedSessionId],
    queryFn: () => api.getSession(resolvedSessionId),
    enabled: !session && !resolvedSessionId.startsWith("mock-"),
    staleTime: 60000,
  })

  useEffect(() => {
    if (fetchedSession && !session) {
      addSession(fetchedSession)
    }
  }, [fetchedSession, session, addSession])

  // Track which sessions have had their history loaded.
  // Using a Set (not a single ID) prevents the bug where switching
  // A→B→A would re-trigger a stale cached fetch that overwrites
  // SSE-pushed messages.
  const historyLoadedRef = useRef<Set<string>>(new Set())
  if (!(historyLoadedRef.current instanceof Set)) historyLoadedRef.current = new Set()
  const hasStoreMessages = !!messagesFromStore?.length
  const needsHistory = !hasStoreMessages && !historyLoadedRef.current.has(resolvedSessionId) && !resolvedSessionId.startsWith("mock-")

  const { data: historyMessages } = useQuery({
    queryKey: ["messages", authUserId, resolvedSessionId],
    queryFn: () => api.getMessages(resolvedSessionId),
    enabled: needsHistory,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (historyMessages && historyMessages.length > 0) {
      // Only set from history if the store doesn't already have messages
      // (SSE may have pushed messages while we were away)
      const existing = useSessionStore.getState().messages.get(resolvedSessionId)
      if (!existing || existing.length === 0) {
        setMessages(resolvedSessionId, historyMessages)
      }
      historyLoadedRef.current.add(resolvedSessionId)
    }
  }, [historyMessages, resolvedSessionId, setMessages])

  const pendingVariant = useUIStore((s) => s.pendingVariant)

  const handleSend = useCallback(async (text: string) => {
    let realId = useSessionStore.getState().resolveSessionId(sessionId)
    if (realId.startsWith("mock-")) {
      try {
        realId = await useSessionStore.getState().ensureRealSession(sessionId)
      } catch {
        addToast("error", "Failed to create session. Please try again.")
        return
      }
    }

    if (realId !== sessionId) {
      onNavigate(`/session/${realId}`)
    }

    const clientMessageId = globalThis.crypto?.randomUUID?.() ?? `cmid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const optimistic: MessageWithParts = {
      id: `tmp-${clientMessageId}`,
      session_id: realId,
      role: "user",
      parts: [{ type: "text", id: `tmp-part-${clientMessageId}`, text }],
      created_at: new Date().toISOString(),
      client_message_id: clientMessageId,
    }
    addMessage(realId, optimistic)

    try {
      const options: { variant?: string; clientMessageId: string } = { clientMessageId }
      if (pendingVariant) options.variant = pendingVariant
      await api.sendMessageAsync(realId, text, Object.keys(options).length > 0 ? options : undefined)
    } catch {
      const list = useSessionStore.getState().messages.get(realId) || []
      useSessionStore.getState().setMessages(
        realId,
        list.filter((m) => m.id !== optimistic.id),
      )
      addToast("error", "Failed to send message. Please try again.")
    }
  }, [sessionId, addToast, pendingVariant, addMessage, onNavigate])

  const handleAbort = useCallback(() => {
    const realId = useSessionStore.getState().resolveSessionId(sessionId)
    if (realId.startsWith("mock-")) return
    api.abortSession(realId).catch(() => {
      addToast("error", "Failed to stop the agent.")
    })
  }, [sessionId, addToast])

  return (
    <div className="flex flex-col h-full bg-[hsl(var(--background))] grid-pattern">
      <BrowserUseBanner />
      {isPlanMode && (
        <PlanBanner
          planPath={session?.slug ? `.openbox/plans/...-${session.slug}.md` : undefined}
        />
      )}
      <div className="flex-1 overflow-hidden">
        <MessageList
          messages={messages}
          sessionId={resolvedSessionId}
          isBusy={isBusy}
        />
      </div>

      {/* Inline question cards (also handles plan_exit approval) */}
      {pendingQuestions.map((q) => (
        <QuestionCard key={q.id} request={q} />
      ))}

      <InputBar
        onSend={handleSend}
        onAbort={handleAbort}
        isBusy={isBusy}
        sessionId={resolvedSessionId}
        statusText={busyStatusText}
      />

      {/* Permission dialogs */}
      {pendingPermissions.map((p) => (
        <PermissionDialog key={p.id} request={p} />
      ))}
    </div>
  )
}
