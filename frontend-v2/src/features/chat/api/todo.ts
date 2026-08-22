import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { TodoList } from "@/shared/types/api"
import { chatKeys } from "./keys"
import { useUserId } from "./messages"

export function useTodoQuery(sessionId: string, enabled = true) {
  const userId = useUserId()
  return useQuery({
    queryKey: chatKeys.todo(userId, sessionId),
    queryFn: () => http.get<TodoList>(`/api/agent/session/${sessionId}/todo`),
    enabled: enabled && sessionId.length > 0,
  })
}

/** Put a task of the user's own on the list, optionally after a given one. */
export function useAddTodoItem(sessionId: string) {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ subject, afterId }: { subject: string; afterId?: string }) =>
      http.post<TodoList>(`/api/agent/session/${sessionId}/todo/items`, {
        subject,
        after_id: afterId ?? null,
      }),
    // The response is the merged list, so it seeds the cache directly rather
    // than costing a refetch. The WS echo arrives right behind it and agrees.
    onSuccess: (list) => qc.setQueryData(chatKeys.todo(userId, sessionId), list),
  })
}

/** Drop a task. The user's own goes away; the model's is marked cancelled. */
export function useRemoveTodoItem(sessionId: string) {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: string) =>
      http.delete<TodoList>(`/api/agent/session/${sessionId}/todo/items/${itemId}`),
    onSuccess: (list) => qc.setQueryData(chatKeys.todo(userId, sessionId), list),
  })
}
