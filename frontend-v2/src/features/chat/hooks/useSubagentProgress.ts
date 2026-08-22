// What a subagent is doing right now, for the row that spawned it.
//
// A `task` call used to render as one line — "call tool · running" — for as
// long as the child took, which is often minutes. Everything the subagent did
// was already arriving in this client: a child session is a session, and its
// message and part events stream over the same socket, keyed by its own id.
// Nothing was reading them.
//
// So this reads them. No new endpoint, no polling — the store already has it.
import { useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { MessageWithParts, ToolPart } from "@/shared/types/api"
import { useStreamStore } from "../stores/stream"
import { toolDuration } from "../lib/turn-view"

export interface SubagentProgress {
  /** The child session, when the task announced one. */
  sessionId?: string
  /** Which agent was spawned, e.g. "explore". */
  agent?: string
  /** Calls the subagent has made. */
  toolCount: number
  /** The call it is making now, if any. */
  current?: ToolPart
  /** Seconds of tool time the child has accounted for. */
  seconds: number
}

/** Read the child session id a task tool recorded on its part. */
export function childSessionOf(part: ToolPart): string | undefined {
  const value = part.metadata?.child_session_id
  return typeof value === "string" && value ? value : undefined
}

function agentOf(part: ToolPart): string | undefined {
  const value = part.metadata?.subagent_type
  return typeof value === "string" && value ? value : undefined
}

/** Live progress for one task call. Returns zeroed progress for a part that
 *  is not a task, or whose child has not reported anything yet. */
export function useSubagentProgress(part: ToolPart): SubagentProgress {
  const sessionId = childSessionOf(part)
  const messages = useStreamStore((s) => (sessionId ? s.messages.get(sessionId) : undefined))

  // While the parent runs, the child's parts arrive over the socket and the
  // store fills itself. A conversation opened afterwards never saw those
  // events, so the child is fetched once — the same thing opencode's TUI does
  // when a task row mounts. Only when there is nothing yet, so a live run is
  // never disturbed by a refetch.
  const empty = Boolean(sessionId) && !messages?.length
  const { data: fetched } = useQuery({
    queryKey: ["subagent-messages", sessionId],
    queryFn: () => http.get<MessageWithParts[]>(`/api/agent/session/${sessionId}/message`),
    enabled: empty,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (sessionId && fetched?.length) useStreamStore.getState().setMessages(sessionId, fetched)
  }, [sessionId, fetched])

  return useMemo(() => {
    const agent = agentOf(part)
    if (!sessionId || !messages) return { sessionId, agent, toolCount: 0, seconds: 0 }

    const tools = messages.flatMap((m) =>
      m.parts.filter((p): p is ToolPart => p.type === "tool"),
    )
    const running = tools.filter((t) => t.status === "running" || t.status === "pending")
    return {
      sessionId,
      agent,
      toolCount: tools.length,
      // The newest running call: that is the one it is on. Falling back to the
      // last finished one keeps the row from going blank in the gap between
      // two calls, which is where most of a subagent's time actually goes.
      current: running[running.length - 1] ?? tools[tools.length - 1],
      seconds: tools.reduce((sum, t) => sum + (toolDuration(t) ?? 0), 0),
    }
  }, [part, sessionId, messages])
}
