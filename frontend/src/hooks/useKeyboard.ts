import { useEffect } from "react"
import { useUIStore } from "@/stores/ui"

export function useKeyboard() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey

      // Cmd/Ctrl + K -> Command Palette
      if (meta && e.key === "k") {
        e.preventDefault()
        useUIStore.getState().setCommandPaletteOpen(true)
      }

      // Escape -> Close modals/command palette
      if (e.key === "Escape") {
        const ui = useUIStore.getState()
        if (ui.commandPaletteOpen) {
          ui.setCommandPaletteOpen(false)
        }
      }

      // Ctrl + ` -> Toggle terminal
      if (e.ctrlKey && e.key === "`") {
        e.preventDefault()
        useUIStore.getState().toggleBottomPanel()
      }

      // Cmd/Ctrl + B -> Toggle sidebar
      if (meta && e.key === "b") {
        e.preventDefault()
        useUIStore.getState().toggleSidebar()
      }
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])
}
