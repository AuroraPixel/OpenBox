import { useRef, useCallback } from "react"
import { GripHorizontal } from "lucide-react"
import { useUIStore } from "@/stores/ui"
import { useTerminalStore } from "@/stores/terminal"
import { TerminalTabs } from "@/components/terminal/TerminalTabs"
import type { ContainerInfo } from "@/types"

interface BottomPanelProps {
  containers: ContainerInfo[]
}

export function BottomPanel({ containers }: BottomPanelProps) {
  const bottomPanelOpen = useUIStore((s) => s.bottomPanelOpen)
  const bottomPanelHeight = useUIStore((s) => s.bottomPanelHeight)
  const setBottomPanelHeight = useUIStore((s) => s.setBottomPanelHeight)
  const tabs = useTerminalStore((s) => s.tabs)
  const activeTabId = useTerminalStore((s) => s.activeTabId)
  const setActive = useTerminalStore((s) => s.setActive)
  const closeTab = useTerminalStore((s) => s.closeTab)

  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startY: e.clientY, startHeight: bottomPanelHeight }

    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startY - e.clientY
      setBottomPanelHeight(dragRef.current.startHeight + delta)
    }

    const handleMouseUp = () => {
      dragRef.current = null
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)
  }, [bottomPanelHeight, setBottomPanelHeight])

  // Touch support for mobile drag
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0]
    if (!touch) return
    dragRef.current = { startY: touch.clientY, startHeight: bottomPanelHeight }

    const handleTouchMove = (e: TouchEvent) => {
      if (!dragRef.current || !e.touches[0]) return
      const delta = dragRef.current.startY - e.touches[0].clientY
      setBottomPanelHeight(dragRef.current.startHeight + delta)
    }

    const handleTouchEnd = () => {
      dragRef.current = null
      document.removeEventListener("touchmove", handleTouchMove)
      document.removeEventListener("touchend", handleTouchEnd)
    }

    document.addEventListener("touchmove", handleTouchMove, { passive: false })
    document.addEventListener("touchend", handleTouchEnd)
  }, [bottomPanelHeight, setBottomPanelHeight])

  if (!bottomPanelOpen || tabs.length === 0) return null

  return (
    <div
      className="border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] flex flex-col shrink-0"
      style={{ height: Math.min(bottomPanelHeight, typeof window !== "undefined" ? window.innerHeight * 0.6 : 400) }}
    >
      {/* Drag handle — supports both mouse and touch */}
      <div
        className="flex items-center justify-center h-6 sm:h-5 cursor-row-resize hover:bg-[hsl(var(--primary))]/5 transition-colors group border-b border-[hsl(var(--border))] touch-none"
        onMouseDown={handleMouseDown}
        onTouchStart={handleTouchStart}
      >
        <GripHorizontal className="h-3 w-3 text-[hsl(var(--muted-foreground))]/40 group-hover:text-[hsl(var(--primary))] group-hover:glow-cyan" />
      </div>

      {/* Terminal content */}
      <div className="flex-1 overflow-hidden">
        <TerminalTabs
          tabs={tabs.map((t) => ({ containerId: t.containerId, containerName: t.containerName }))}
          activeTab={tabs.find((t) => t.id === activeTabId)?.containerId || null}
          containers={containers}
          onSelectTab={(containerId) => {
            const tab = tabs.find((t) => t.containerId === containerId)
            if (tab) setActive(tab.id)
          }}
          onCloseTab={(containerId) => {
            const tab = tabs.find((t) => t.containerId === containerId)
            if (tab) closeTab(tab.id)
          }}
        />
      </div>
    </div>
  )
}
