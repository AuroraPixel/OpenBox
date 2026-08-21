import { useQuery } from "@tanstack/react-query"
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
