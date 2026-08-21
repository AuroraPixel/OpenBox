import { Suspense, useEffect } from "react"
import { Outlet, useParams } from "react-router"
import { Sidebar, Topbar, useWorkspaceEvents } from "@/features/workspace"
import { WorkbenchPanel, usePanelStore, usePanelEvents } from "@/features/workbench"
import { Spinner } from "@/shared/ui/Spinner"
import { useAuthStore } from "@/shared/api/auth-store"
import { useAppearanceStore } from "@/shared/appearance/store"
import { http } from "@/shared/api/http"
import type { UserPreferences } from "@/shared/types/api"

export default function WorkspaceLayout() {
  useWorkspaceEvents()
  usePanelEvents()
  const { sessionId } = useParams()
  const panelOpen = usePanelStore((s) => s.open)
  const togglePanel = usePanelStore((s) => s.togglePanel)
  const userId = useAuthStore((s) => s.user?.id)

  // Hydrate appearance from server prefs once per signed-in user.
  useEffect(() => {
    if (!userId) return
    void http
      .get<UserPreferences>("/api/auth/me/preferences")
      .then((prefs) => useAppearanceStore.getState().hydrateFromServer(prefs))
      .catch(() => undefined)
  }, [userId])

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-ink">
      <Sidebar />
      <main className="flex min-h-0 min-w-105 flex-1 flex-col overflow-hidden">
        <Topbar panelOpen={panelOpen} onTogglePanel={togglePanel} />
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <Suspense
            fallback={
              <div className="flex flex-1 items-center justify-center">
                <Spinner className="size-5" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </div>
      </main>
      {/* Own boundary: the panel loads its i18n namespace on first open, and
          without this that suspension escapes to the router boundary and blanks
          the whole workspace. */}
      <Suspense fallback={null}>
        <WorkbenchPanel sessionId={sessionId ?? null} />
      </Suspense>
    </div>
  )
}
