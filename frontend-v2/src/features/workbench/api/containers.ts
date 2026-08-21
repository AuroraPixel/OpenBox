// Feature hooks wrapping the shared containers client. Keys come from the shared
// `containerKeys` factory so the sandbox gate (chat composer) and the workbench
// share one cache.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { containerKeys, containersApi } from "@/shared/api/containers"
import type { ContainerInfo } from "@/shared/types/api"
import { useUserId } from "./keys"

export function useContainersQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: containerKeys.all(userId),
    queryFn: () => containersApi.list(),
    refetchInterval: 5000,
  })
}

/** The first running container — treated as "the current sandbox". */
export function useRunningContainer(): ContainerInfo | null {
  const { data } = useContainersQuery()
  return data?.containers?.find((c) => c.status === "running") ?? null
}

export function useCreateContainer() {
  const userId = useUserId()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name?: string) => containersApi.create(name),
    onSuccess: () => void qc.invalidateQueries({ queryKey: containerKeys.all(userId) }),
  })
}
