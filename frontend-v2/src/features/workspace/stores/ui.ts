// Workspace shell UI state: sidebar width/collapse, which project rows are
// expanded, and which project is the current working one (new chats land in
// it). Pure client state (ENGINEERING_SPEC §7.1). Expansion and selection are
// persisted: losing them to a reload or a "new chat" reads as the sidebar
// forgetting where the user was working.
import { create } from "zustand"

interface WorkspaceUiState {
  sidebarWidth: number
  sidebarCollapsed: boolean
  expanded: Record<string, boolean>
  selectedProject: string | null
  setSidebarWidth: (w: number) => void
  toggleSidebar: () => void
  toggleProject: (id: string) => void
  isExpanded: (id: string) => boolean
  selectProject: (id: string | null) => void
}

const KEY = "bossip:workspace-ui"

interface Persisted {
  sidebarWidth?: number
  sidebarCollapsed?: boolean
  expanded?: Record<string, boolean>
  selectedProject?: string | null
}

function readLocal(): Persisted {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Persisted
  } catch {
    return {}
  }
}

export const useWorkspaceUi = create<WorkspaceUiState>((set, get) => {
  const local = readLocal()
  const persist = () => {
    const s = get()
    localStorage.setItem(
      KEY,
      JSON.stringify({
        sidebarWidth: s.sidebarWidth,
        sidebarCollapsed: s.sidebarCollapsed,
        expanded: s.expanded,
        selectedProject: s.selectedProject,
      }),
    )
  }
  return {
    sidebarWidth: Math.min(420, Math.max(220, local.sidebarWidth ?? 280)),
    sidebarCollapsed: local.sidebarCollapsed ?? false,
    expanded: local.expanded ?? {},
    selectedProject: local.selectedProject ?? null,
    setSidebarWidth: (w) => {
      set({ sidebarWidth: Math.min(420, Math.max(220, w)), sidebarCollapsed: false })
      persist()
    },
    toggleSidebar: () => {
      set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed }))
      persist()
    },
    toggleProject: (id) => {
      set((s) => ({ expanded: { ...s.expanded, [id]: !(s.expanded[id] ?? true) } }))
      persist()
    },
    isExpanded: (id) => get().expanded[id] ?? true,
    selectProject: (id) => {
      set({ selectedProject: id })
      persist()
    },
  }
})
