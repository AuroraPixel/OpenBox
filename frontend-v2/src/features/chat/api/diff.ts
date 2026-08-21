// Session diff for the inline patch preview. Deliberately reuses the exact
// query key the workbench panel uses (["diff", userId, sessionId]) so the two
// features share one cache entry instead of each fetching the same payload.
import { useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { DiffEntry } from "@/shared/types/api"
import { useUserId } from "./messages"

const sessionDiffKey = (userId: string, sessionId: string) => ["diff", userId, sessionId] as const
const fetchSessionDiff = (sessionId: string) =>
  http.get<DiffEntry[]>(`/api/agent/session/${sessionId}/diff?full=true`)

export function useSessionDiff(sessionId: string | null, enabled: boolean) {
  const userId = useUserId()
  return useQuery({
    queryKey: sessionDiffKey(userId, sessionId ?? "none"),
    queryFn: () => fetchSessionDiff(sessionId ?? ""),
    enabled: enabled && !!sessionId,
    staleTime: 15_000,
  })
}

/**
 * Warms the review panel's cache before it mounts. The panel only fetches once
 * the user has clicked through to it, so it renders empty for a whole
 * round-trip — pointing at a change card is enough lead time to hide that.
 */
export function usePrefetchSessionDiff(sessionId: string | null): () => void {
  const qc = useQueryClient()
  const userId = useUserId()
  return useCallback(() => {
    if (!sessionId) return
    void qc.prefetchQuery({
      queryKey: sessionDiffKey(userId, sessionId),
      queryFn: () => fetchSessionDiff(sessionId),
      staleTime: 15_000,
    })
  }, [qc, userId, sessionId])
}
