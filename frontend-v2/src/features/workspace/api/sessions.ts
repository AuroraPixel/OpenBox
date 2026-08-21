import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { Session } from "@/shared/types/api"
import { workspaceKeys } from "./keys"
import { useUserId } from "./projects"

export function useSessionsQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: workspaceKeys.sessions(userId),
    // Fetch all sessions once; the sidebar groups by project client-side so
    // switching projects never refetches.
    queryFn: () => http.get<Session[]>("/api/agent/session"),
    staleTime: 30_000,
  })
}

export function useRenameSession() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) =>
      http.patch<Session>(`/api/agent/session/${id}`, { title }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: workspaceKeys.sessions(userId) }),
  })
}

export function useDeleteSession() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => http.delete<{ ok: boolean }>(`/api/agent/session/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: workspaceKeys.sessions(userId) }),
  })
}
