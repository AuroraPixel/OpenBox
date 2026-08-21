// Query key factory + current-user id. Every key carries the user id so
// switching accounts can never serve another user's cache (ENGINEERING_SPEC §7.2).
// Container/file-list keys reuse shared `containerKeys`; only workbench-owned
// keys (diff, file content) live here.
import { useAuthStore } from "@/shared/api/auth-store"

export function useUserId(): string {
  return useAuthStore((s) => s.user?.id ?? "anonymous")
}

export const workbenchKeys = {
  diff: (userId: string, sessionId: string) => ["diff", userId, sessionId] as const,
  fileContent: (containerId: string, path: string) =>
    ["container-file-content", containerId, path] as const,
  workdir: (userId: string, sessionId: string) => ["session-workdir", userId, sessionId] as const,
}
