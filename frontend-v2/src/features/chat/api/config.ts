import { useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { AppConfig } from "@/shared/types/api"
import { chatKeys } from "./keys"
import { useUserId } from "./messages"

export function useConfigQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: chatKeys.config(userId),
    queryFn: () => http.get<AppConfig>("/api/agent/config"),
    staleTime: 5 * 60_000,
  })
}
