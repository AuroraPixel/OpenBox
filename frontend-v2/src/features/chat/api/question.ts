import { useMutation, useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { QuestionRequest } from "@/shared/types/api"
import { usePendingStore } from "../stores/pending"
import { chatKeys } from "./keys"
import { useUserId } from "./messages"

export function useQuestionsQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: chatKeys.questions(userId),
    queryFn: () => http.get<QuestionRequest[]>("/api/agent/question"),
  })
}

export function useReplyQuestion() {
  return useMutation({
    // One array of chosen labels per question, in the order they were asked —
    // the shape the server has always expected. It used to be sent flat, so a
    // reply was rejected before it reached the agent.
    mutationFn: ({ requestId, answers }: { requestId: string; answers: string[][] }) =>
      http.post<{ ok: boolean }>(`/api/agent/question/${requestId}`, { answers }),
    onSuccess: (_data, { requestId }) => usePendingStore.getState().removeQuestion(requestId),
  })
}

export function useRejectQuestion() {
  return useMutation({
    mutationFn: (requestId: string) => http.post<{ ok: boolean }>(`/api/agent/question/${requestId}/reject`),
    onSuccess: (_data, requestId) => usePendingStore.getState().removeQuestion(requestId),
  })
}
