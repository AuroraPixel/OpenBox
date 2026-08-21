import { useNavigate, useSearchParams } from "react-router"
import { paths } from "@/shared/router/paths"
import { Composer, EmptyState, useStartChat } from "@/features/chat"

/** The "/app" index: greeting + composer. First send creates the session. */
export default function EmptyChatRoute() {
  const [params] = useSearchParams()
  const projectId = params.get("project") ?? undefined
  const navigate = useNavigate()
  const start = useStartChat((sessionId) => navigate(paths.chat(sessionId)))

  return (
    <div className="flex h-full min-h-0 flex-col">
      <EmptyState onPick={(text) => void start(text, { projectId })} />
      <Composer
        busy={false}
        autoFocus
        onSubmit={(text, opts) => void start(text, { ...opts, projectId })}
      />
    </div>
  )
}
