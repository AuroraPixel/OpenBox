import { useMutation, useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import type { PermissionRequest } from "@/shared/types/api"
import { usePendingStore } from "../stores/pending"
import { chatKeys } from "./keys"
import { useUserId } from "./messages"

export type PermissionAction = "allow" | "allow_always" | "reject"

export function usePermissionsQuery() {
  const userId = useUserId()
  return useQuery({
    queryKey: chatKeys.permissions(userId),
    queryFn: () => http.get<PermissionRequest[]>("/api/agent/permission"),
  })
}

export function useReplyPermission() {
  return useMutation({
    mutationFn: ({ requestId, action }: { requestId: string; action: PermissionAction }) =>
      http.post<{ ok: boolean }>(`/api/agent/permission/${requestId}`, { action }),
    onSuccess: (_data, { requestId }) => usePendingStore.getState().removePermission(requestId),
  })
}
