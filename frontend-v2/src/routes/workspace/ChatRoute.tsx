import { useEffect, useMemo, useState } from "react"
import { useParams } from "react-router"
import { Spinner } from "@/shared/ui/Spinner"
import { toast } from "@/shared/ui/Toast"
import { useApiErrorMessage } from "@/shared/hooks/useApiErrorMessage"
import type { MessageWithParts, PermissionRequest, QuestionRequest } from "@/shared/types/api"
import {
  ChatFlow,
  Composer,
  PermissionCard,
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
} from "@/features/chat"
import { useSessionQuery } from "@/features/chat/api/message-actions"
import { useChatAgents, type ChatAgent } from "@/features/chat/api/agents"

const EMPTY_MESSAGES: MessageWithParts[] = []
const EMPTY_PERMS: PermissionRequest[] = []
const EMPTY_QUESTIONS: QuestionRequest[] = []
const EMPTY_AGENTS: ChatAgent[] = []

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
  // A tool part left as "running" is the fallback signal for busy, but only
  // while the session's real status is still unknown — a session opened
  // mid-run reads as busy from this before its first session.status event.
  // Once status is known it is authoritative: pressing stop sets it to idle,
  // and the button must flip at once rather than waiting for the backend to
  // finish tearing down and report the tool aborted. Reading a stale running
  // part as busy after an explicit idle is exactly what made stop feel dead.
  const hasRunningTool = useMemo(
    () =>
      messages.some((m) =>
        m.parts.some((p) => p.type === "tool" && (p.status === "running" || p.status === "pending")),
      ),
    [messages],
  )
  const busy = status === undefined ? hasRunningTool : isBusyStatus(status)

  const session = useSessionQuery(sessionId)
  const send = useSendChat(sessionId)
  const abort = useAbortSession(sessionId)
  const stop = () => {
    abort.mutate()
    useStreamStore.getState().setStatus(sessionId, "idle")
  }

  // Which agent this conversation answers as. The session record is the
  // truth — the backend writes it on every switch, including the model's own
  // plan_enter/plan_exit — with an unsent pick layered on top so the picker
  // reacts before the next message goes out.
  //
  // The pick is dropped by comparing during render rather than in an effect:
  // an effect would render once with the stale pick still showing, which for
  // a mode indicator means briefly claiming the wrong mode.
  const { data: agents } = useChatAgents()
  const serverAgent = session.data?.agent ?? "build"
  const [pickedAgent, setPickedAgent] = useState<string | undefined>(undefined)
  const [seenAgent, setSeenAgent] = useState({ sessionId, serverAgent })
  if (seenAgent.sessionId !== sessionId || seenAgent.serverAgent !== serverAgent) {
    setSeenAgent({ sessionId, serverAgent })
    setPickedAgent(undefined)
  }
  const sessionAgent = pickedAgent ?? serverAgent

  const permissions = usePendingStore((s) => s.permissions.get(sessionId) ?? EMPTY_PERMS)
  const questions = usePendingStore((s) => s.questions.get(sessionId) ?? EMPTY_QUESTIONS)

  const loading = messagesQ.isLoading && messages.length === 0

  // The task list used to live here, as a card pinned under the last turn,
  // fed by a REST query and thrown away when the run ended. It renders inside
  // the turn now (TodoCard), where the calls it organises actually are.
  const footer = (
    <>
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
        <ChatFlow turns={turns} sessionId={sessionId} busy={busy} footer={footer} onStop={stop} />
      )}
      <Composer
        busy={busy}
        onSubmit={(text, opts) => send(text, { ...opts, agent: sessionAgent })}
        onStop={stop}
        sessionModel={session.data?.model}
        sessionKey={sessionId}
        contextTokens={session.data?.token_usage?.context ?? 0}
        contextLimit={session.data?.token_usage?.limit ?? 0}
        agents={agents ?? EMPTY_AGENTS}
        sessionAgent={sessionAgent}
        onPickAgent={setPickedAgent}
      />
    </div>
  )
}
