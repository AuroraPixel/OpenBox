import { useCallback } from "react"
import { useNavigate } from "react-router"
import { useAuthStore } from "@/shared/api/auth-store"
import { paths } from "@/shared/router/paths"

/** Landing CTAs: signed-in visitors jump into the app, others go to sign-in. */
export function useStart() {
  const navigate = useNavigate()
  const authed = useAuthStore((s) => s.isAuthenticated)
  return useCallback(() => navigate(authed ? paths.app : paths.login), [navigate, authed])
}
