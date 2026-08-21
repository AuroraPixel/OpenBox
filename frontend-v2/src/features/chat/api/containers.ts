// Running-sandbox lookup for the composer's attachment upload target.
// Shares containerKeys with the workbench feature so the cache dedupes.
import { useQuery } from "@tanstack/react-query"
import { containersApi, containerKeys } from "@/shared/api/containers"
import { useAuthStore } from "@/shared/api/auth-store"

export function useRunningContainer() {
  const userId = useAuthStore((s) => s.user?.id ?? "anonymous")
  const query = useQuery({
    queryKey: containerKeys.all(userId),
    queryFn: () => containersApi.list(),
    staleTime: 15_000,
  })
  return query.data?.containers.find((c) => c.status === "running") ?? null
}
