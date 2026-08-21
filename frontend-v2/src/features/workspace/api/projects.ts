import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import { useAuthStore } from "@/shared/api/auth-store"
import type { Project } from "@/shared/types/api"
import { workspaceKeys } from "./keys"

export function useUserId(): string {
  return useAuthStore((s) => s.user?.id ?? "anonymous")
}

export function useProjectsQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: workspaceKeys.projects(userId),
    queryFn: () => http.get<Project[]>("/api/agent/project"),
  })
}

export function useCreateProject() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => http.post<Project>("/api/agent/project", { name }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: workspaceKeys.projects(userId) }),
  })
}

export function useRenameProject() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      http.patch<Project>(`/api/agent/project/${id}`, { name }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: workspaceKeys.projects(userId) }),
  })
}

export function useDeleteProject() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => http.delete<{ ok: boolean }>(`/api/agent/project/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workspaceKeys.projects(userId) })
      void qc.invalidateQueries({ queryKey: workspaceKeys.sessions(userId) })
    },
  })
}
