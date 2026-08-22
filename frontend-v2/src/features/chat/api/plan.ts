import { useMutation } from "@tanstack/react-query"
import { http } from "@/shared/api/http"

/** Accept/reject a plan-mode proposal (plan part with status "ready"). */
export function usePlanDecision(sessionId: string) {
  const accept = useMutation({
    mutationFn: () => http.post<{ ok: boolean }>(`/api/agent/session/${sessionId}/plan/accept`),
  })
  const reject = useMutation({
    mutationFn: () => http.post<{ ok: boolean }>(`/api/agent/session/${sessionId}/plan/reject`),
  })
  return { accept, reject }
}

/** Save the user's edits to the plan.
 *
 *  The card updates from the plan part the server echoes back, not from local
 *  state: the same write also moves the file the build agent will read, and
 *  those two must never disagree about what was approved.
 */
export function useSavePlan(sessionId: string) {
  return useMutation({
    mutationFn: (content: string) =>
      http.put<{ ok: boolean; path: string }>(`/api/agent/session/${sessionId}/plan`, { content }),
  })
}
