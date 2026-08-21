import { type ReactNode } from "react"
import { Navigate, useLocation } from "react-router"
import { useAuthStore } from "@/shared/api/auth-store"
import { FullScreenLoader } from "@/app/providers/AppProviders"
import { paths } from "@/app/router/paths"

export function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  const location = useLocation()

  if (isLoading) return <FullScreenLoader />
  if (!isAuthenticated) {
    return <Navigate to={paths.login} state={{ from: location.pathname }} replace />
  }
  return children
}

export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  if (isLoading) return <FullScreenLoader />
  if (isAuthenticated) return <Navigate to={paths.app} replace />
  return children
}
