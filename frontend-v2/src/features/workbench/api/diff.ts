// Session diff query — `GET /api/agent/session/{id}/diff` → DiffEntry[].
// Invalidated by `usePanelEvents` when the backend publishes `session.diff`.
import { useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { DiffEntry } from "@/shared/types/api"
import { useUserId, workbenchKeys } from "./keys"

export function useDiffQuery(sessionId: string | null) {
  const userId = useUserId()
  return useQuery({
    queryKey: workbenchKeys.diff(userId, sessionId ?? "none"),
    queryFn: () => http.get<DiffEntry[]>(`/api/agent/session/${sessionId}/diff?full=true`),
    enabled: !!sessionId,
  })
}
