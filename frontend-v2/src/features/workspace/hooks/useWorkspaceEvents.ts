// WS → session-list bridge: keeps sidebar/topbar session state fresh.
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { wsClient } from "@/shared/ws/client"
import { useAuthStore } from "@/shared/api/auth-store"
import { workspaceKeys } from "../api/keys"

export function useWorkspaceEvents() {
  const qc = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? "anonymous")

  useEffect(() => {
    void wsClient.connect()
    const invalidate = () => void qc.invalidateQueries({ queryKey: workspaceKeys.sessions(userId) })
    const subs = [
      wsClient.on("session.status", invalidate),
      wsClient.on("session.title", invalidate),
      wsClient.on("session.updated", invalidate),
      wsClient.on("__connected", invalidate),
    ]
    return () => subs.forEach((off) => off())
  }, [qc, userId])

  useEffect(() => {
    return () => {
      // Disconnect only when the workspace unmounts entirely (sign-out).
      wsClient.disconnect()
    }
  }, [])
}
