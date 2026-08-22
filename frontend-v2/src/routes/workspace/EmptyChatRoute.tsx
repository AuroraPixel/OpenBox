import { useState } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { paths } from "@/shared/router/paths"
import { Composer, EmptyState, useChatAgents, useStartChat } from "@/features/chat"
import type { ChatAgent } from "@/features/chat/api/agents"

const EMPTY_AGENTS: ChatAgent[] = []

/** The "/app" index: greeting + composer. First send creates the session. */
export default function EmptyChatRoute() {
  const [params] = useSearchParams()
  const projectId = params.get("project") ?? undefined
  const navigate = useNavigate()
  const start = useStartChat((sessionId) => navigate(paths.chat(sessionId)))

  // The mode is picked before the session exists, and carried into its
  // creation — starting a conversation in plan mode is exactly when someone
  // wants plan mode, and making them send once in build first would defeat it.
  const { data: agents } = useChatAgents()
  const [agent, setAgent] = useState("build")

  return (
    <div className="flex h-full min-h-0 flex-col">
      <EmptyState onPick={(text) => void start(text, { projectId, agent })} />
      <Composer
        busy={false}
        autoFocus
        onSubmit={(text, opts) => void start(text, { ...opts, projectId, agent })}
        agents={agents ?? EMPTY_AGENTS}
        sessionAgent={agent}
        onPickAgent={setAgent}
      />
    </div>
  )
}
