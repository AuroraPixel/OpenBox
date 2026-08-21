// The directory a session's tools run in (/workspace/<project-slug>), from the
// session detail endpoint. The files panel roots its tree here: /workspace is
// the agent's whole activity space, not the project the user is working on.
import { useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import { useUserId, workbenchKeys } from "./keys"

interface SessionDetail {
  directory?: string
}

export function useSessionWorkdir(sessionId: string | null): string | null {
  const userId = useUserId()
  const { data } = useQuery({
    queryKey: workbenchKeys.workdir(userId, sessionId ?? "none"),
    queryFn: () => http.get<SessionDetail>(`/api/agent/session/${sessionId}`),
    enabled: !!sessionId,
    // A session's project can change only by moving the session; near-static.
    staleTime: 5 * 60_000,
  })
  return data?.directory ?? null
}
