// Workbench panel UI state: the right-hand work surface (review / terminal /
// browser / files) as a tabbed panel. Pure client state (ENGINEERING_SPEC §7.1).
// openKind/togglePanel semantics are ported from the design reference.
import { create } from "zustand"

export type TabKind = "menu" | "review" | "terminal" | "browser" | "files" | "desktop"

export interface PanelTab {
  id: string
  kind: TabKind
}

/** Extra state carried by openKind — which file the target tab should focus. */
export interface OpenExtra {
  reviewFile?: string | null
  openFile?: string | null
}

interface PanelState {
  open: boolean
  width: number
  tabs: PanelTab[]
  activeTabId: string | null
  reviewFile: string | null
  openFile: string | null
  treeOpen: boolean
  treeWidth: number
  seq: number

  togglePanel: () => void
  setWidth: (w: number) => void
  addTab: () => void
  closeTab: (id: string) => void
  selectTab: (id: string) => void
  openKind: (kind: TabKind, extra?: OpenExtra) => void
  setReviewFile: (path: string | null) => void
  setOpenFile: (path: string | null) => void
  toggleTree: () => void
  setTreeWidth: (w: number) => void
}

const KEY = "bossip:workbench-panel"
const WIDTH_MIN = 360
const WIDTH_MAX = 1000
const TREE_MIN = 170

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v))

function readLocal(): { width?: number; treeWidth?: number; treeOpen?: boolean } {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, never>
  } catch {
    return {}
  }
}

/** Only keys the store owns — protects `set` from stray extra fields. */
function normalizeExtra(extra?: OpenExtra): Partial<PanelState> {
  const patch: Partial<PanelState> = {}
  if (extra && "reviewFile" in extra) patch.reviewFile = extra.reviewFile ?? null
  if (extra && "openFile" in extra) patch.openFile = extra.openFile ?? null
  return patch
}

export const usePanelStore = create<PanelState>((set, get) => {
  const local = readLocal()
  const persist = () => {
    const s = get()
    localStorage.setItem(
      KEY,
      JSON.stringify({ width: s.width, treeWidth: s.treeWidth, treeOpen: s.treeOpen }),
    )
  }

  return {
    open: false,
    width: clamp(local.width ?? 640, WIDTH_MIN, WIDTH_MAX),
    tabs: [],
    activeTabId: null,
    reviewFile: null,
    openFile: null,
    treeOpen: local.treeOpen ?? true,
    treeWidth: Math.max(TREE_MIN, local.treeWidth ?? 250),
    seq: 1,

    togglePanel: () =>
      set((x) => {
        if (x.open) return { open: false }
        if (x.tabs.length) return { open: true }
        const id = `t${x.seq}`
        return { open: true, seq: x.seq + 1, activeTabId: id, tabs: [{ id, kind: "menu" }] }
      }),

    setWidth: (w) => {
      set({ width: clamp(w, WIDTH_MIN, WIDTH_MAX) })
      persist()
    },

    addTab: () =>
      set((x) => {
        const id = `t${x.seq}`
        return { seq: x.seq + 1, activeTabId: id, tabs: [...x.tabs, { id, kind: "menu" }] }
      }),

    closeTab: (id) =>
      set((x) => {
        const tabs = x.tabs.filter((tb) => tb.id !== id)
        const activeTabId =
          x.activeTabId === id ? (tabs.length ? tabs[tabs.length - 1].id : null) : x.activeTabId
        return { tabs, activeTabId, open: tabs.length > 0 }
      }),

    selectTab: (id) => set({ activeTabId: id }),

    openKind: (kind, extra) =>
      set((x) => {
        const patch = { open: true, ...normalizeExtra(extra) }
        const active = x.tabs.find((tb) => tb.id === x.activeTabId)
        if (active && active.kind === kind) return patch
        const hit = x.tabs.find((tb) => tb.kind === kind)
        if (hit) return { ...patch, activeTabId: hit.id }
        // No same-kind tab yet: convert an active "menu" tab in place (design's
        // menu-open behaviour), otherwise append a fresh tab.
        if (active && active.kind === "menu") {
          return { ...patch, tabs: x.tabs.map((tb) => (tb.id === active.id ? { ...tb, kind } : tb)) }
        }
        const id = `t${x.seq}`
        return { ...patch, seq: x.seq + 1, activeTabId: id, tabs: [...x.tabs, { id, kind }] }
      }),

    setReviewFile: (reviewFile) => set({ reviewFile }),
    setOpenFile: (openFile) => set({ openFile }),

    toggleTree: () => {
      set((x) => ({ treeOpen: !x.treeOpen }))
      persist()
    },

    setTreeWidth: (w) => {
      set((x) => ({ treeWidth: clamp(w, TREE_MIN, Math.max(TREE_MIN + 10, x.width - 280)) }))
      persist()
    },
  }
})
