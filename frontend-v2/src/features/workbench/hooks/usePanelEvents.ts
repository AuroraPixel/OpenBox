// Mount-once wiring between cross-feature signals and the panel:
//  - chat emits `workbench.open` (click "审阅" etc.) → open the matching tab.
//  - backend publishes `session.diff` over the WS → invalidate the diff query.
// Mounted a single time at the layout level; imports no other feature.
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import i18n from "@/shared/i18n"
import { onAppEvent } from "@/shared/events/bus"
import { wsClient } from "@/shared/ws/client"
import { usePanelStore } from "@/features/workbench/stores/panel"
import { useUserId } from "@/features/workbench/api/keys"
import type { OpenExtra } from "@/features/workbench/stores/panel"

export function usePanelEvents(): void {
  const openKind = usePanelStore((s) => s.openKind)
  const qc = useQueryClient()
  const userId = useUserId()

  // Warm the panel's namespace while the panel is still closed, so opening it
  // never has to suspend on a locale fetch.
  useEffect(() => {
    void i18n.loadNamespaces("workbench")
  }, [])

  useEffect(() => {
    const offOpen = onAppEvent("workbench.open", ({ kind, file }) => {
      const extra: OpenExtra | undefined =
        kind === "review"
          ? { reviewFile: file ?? null }
          : kind === "files"
            ? { openFile: file ?? null }
            : undefined
      openKind(kind, extra)
    })
    const offDiff = wsClient.on("session.diff", () => {
      void qc.invalidateQueries({ queryKey: ["diff", userId] })
    })
    return () => {
      offOpen()
      offDiff()
    }
  }, [openKind, qc, userId])
}
