import { useEffect, useMemo } from "react"
import { useParams } from "react-router"
import { Spinner } from "@/shared/ui/Spinner"
import { toast } from "@/shared/ui/Toast"
import { useApiErrorMessage } from "@/shared/hooks/useApiErrorMessage"
import type { MessageWithParts, PermissionRequest, QuestionRequest } from "@/shared/types/api"
import {
  ChatFlow,
  Composer,
  PermissionCard,
  PlanCard,
  QuestionCard,
  isBusyStatus,
  mergeTurns,
  useAbortSession,
  useChatEvents,
  useMessagesQuery,
  usePendingStore,
  usePermissionsQuery,
  useQuestionsQuery,
  useSendChat,
  useStreamStore,
  useTodoQuery,
} from "@/features/chat"
import { useSessionQuery } from "@/features/chat/api/message-actions"

const EMPTY_MESSAGES: MessageWithParts[] = []
const EMPTY_PERMS: PermissionRequest[] = []
const EMPTY_QUESTIONS: QuestionRequest[] = []

export default function ChatRoute() {
  const { sessionId = "" } = useParams()
  useChatEvents(sessionId)

  const messagesQ = useMessagesQuery(sessionId)
  const permsQ = usePermissionsQuery()
  const questionsQ = useQuestionsQuery()
  const errorMessage = useApiErrorMessage()

  // Snapshot → stream store. setMessages merges so it never clobbers live deltas.
  useEffect(() => {
    if (messagesQ.data) useStreamStore.getState().setMessages(sessionId, messagesQ.data)
  }, [messagesQ.data, sessionId])
  useEffect(() => {
    if (permsQ.data) usePendingStore.getState().setPermissions(permsQ.data)
  }, [permsQ.data])
  useEffect(() => {
    if (questionsQ.data) usePendingStore.getState().setQuestions(questionsQ.data)
  }, [questionsQ.data])
  useEffect(() => {
    if (messagesQ.error) toast("error", errorMessage(messagesQ.error))
  }, [messagesQ.error, errorMessage])

  const messages = useStreamStore((s) => s.messages.get(sessionId) ?? EMPTY_MESSAGES)
  const status = useStreamStore((s) => s.status.get(sessionId))
  const turns = useMemo(() => mergeTurns(messages), [messages])
  // Fall back to running-tool detection so a session opened mid-run still reads
  // as busy before the first live session.status event arrives.
  const hasRunningTool = useMemo(
    () =>
      messages.some((m) =>
        m.parts.some((p) => p.type === "tool" && (p.status === "running" || p.status === "pending")),
      ),
    [messages],
  )
  const busy = isBusyStatus(status) || hasRunningTool

  const session = useSessionQuery(sessionId)
  const send = useSendChat(sessionId)
  const abort = useAbortSession(sessionId)
  const stop = () => {
    abort.mutate()
    useStreamStore.getState().setStatus(sessionId, "idle")
  }

  const todoQ = useTodoQuery(sessionId, busy)
  const todoItems = todoQ.data?.items ?? []
  const permissions = usePendingStore((s) => s.permissions.get(sessionId) ?? EMPTY_PERMS)
  const questions = usePendingStore((s) => s.questions.get(sessionId) ?? EMPTY_QUESTIONS)

  const loading = messagesQ.isLoading && messages.length === 0

  const footer = (
    <>
      {busy && todoItems.length > 0 && <PlanCard items={todoItems} onStop={stop} />}
      {permissions.map((p) => (
        <PermissionCard key={p.id} request={p} />
      ))}
      {questions.map((q) => (
        <QuestionCard key={q.id} request={q} />
      ))}
    </>
  )

  return (
    <div className="flex h-full min-h-0 flex-col">
      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <Spinner className="size-6" />
        </div>
      ) : (
        <ChatFlow turns={turns} sessionId={sessionId} busy={busy} footer={footer} />
      )}
      <Composer
        busy={busy}
        onSubmit={(text, opts) => send(text, opts)}
        onStop={stop}
        sessionModel={session.data?.model}
        sessionKey={sessionId}
        contextTokens={session.data?.token_usage?.context ?? 0}
        contextLimit={session.data?.token_usage?.limit ?? 0}
      />
    </div>
  )
}
