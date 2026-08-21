// The workbench shell: a resizable right-hand panel that hosts the tab bar and
// the active tab. Docked by default; when the window gets tight it floats as an
// overlay (design's overlay mode). A ResizeObserver flags a "narrow" panel so
// the Files tab can collapse to a single column.
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react"
import { cn } from "@/shared/lib/cn"
import { usePanelStore } from "@/features/workbench/stores/panel"
import { PanelTabBar } from "./PanelTabBar"
import { MenuTab } from "./MenuTab"
import { ReviewTab } from "./ReviewTab"
import { TerminalTab } from "./TerminalTab"
import { BrowserTab } from "./BrowserTab"
import { DesktopTab } from "./DesktopTab"
import { FilesTab } from "./FilesTab"

const OVERLAY_GAP = 520
const NARROW_WIDTH = 470
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v))

interface WorkbenchPanelProps {
  sessionId: string | null
}

export function WorkbenchPanel({ sessionId }: WorkbenchPanelProps) {
  const open = usePanelStore((s) => s.open)
  const width = usePanelStore((s) => s.width)
  const tabs = usePanelStore((s) => s.tabs)
  const activeTabId = usePanelStore((s) => s.activeTabId)
  const setWidth = usePanelStore((s) => s.setWidth)

  const [winW, setWinW] = useState(() => window.innerWidth)
  const [narrow, setNarrow] = useState(false)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const onResize = () => setWinW(window.innerWidth)
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  useEffect(() => {
    const el = panelRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver((entries) => setNarrow(entries[0].contentRect.width < NARROW_WIDTH))
    ro.observe(el)
    return () => ro.disconnect()
  }, [open])

  if (!open) return null

  const overlay = winW - width < OVERLAY_GAP
  const overlayWidth = Math.min(width, Math.max(320, winW - 30))
  const kind = tabs.find((tb) => tb.id === activeTabId)?.kind ?? "menu"

  const startDrag = (e: ReactMouseEvent) => {
    e.preventDefault()
    const x0 = e.clientX
    const w0 = usePanelStore.getState().width
    const move = (ev: MouseEvent) => setWidth(clamp(w0 - (ev.clientX - x0), 360, 1000))
    const up = () => {
      window.removeEventListener("mousemove", move)
      window.removeEventListener("mouseup", up)
      document.body.style.userSelect = ""
    }
    window.addEventListener("mousemove", move)
    window.addEventListener("mouseup", up)
    document.body.style.userSelect = "none"
  }

  return (
    <section
      ref={panelRef}
      style={{ width: overlay ? overlayWidth : width }}
      className={cn(
        "flex min-h-0 flex-col",
        overlay
          ? "fixed end-2.5 top-2.5 bottom-2.5 z-40 rounded-xl border border-hair bg-card shadow-pop"
          : "border-hair relative flex-none border-s bg-rail",
      )}
    >
      <div onMouseDown={startDrag} className="absolute top-0 bottom-0 -left-1.5 z-10 w-2 cursor-col-resize" />
      <PanelTabBar />
      {kind === "menu" && <MenuTab sessionId={sessionId} />}
      {kind === "review" && <ReviewTab sessionId={sessionId} />}
      {kind === "terminal" && <TerminalTab />}
      {kind === "browser" && <BrowserTab />}
      {kind === "files" && <FilesTab narrow={narrow} sessionId={sessionId} />}
      {kind === "desktop" && <DesktopTab />}
    </section>
  )
}
