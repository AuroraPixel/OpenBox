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
