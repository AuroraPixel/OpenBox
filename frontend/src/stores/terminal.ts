import { create } from "zustand"

export interface TerminalTab {
  id: string
  containerId: string
  containerName: string
}

interface TerminalStore {
  tabs: TerminalTab[]
  activeTabId: string | null

  openTerminal: (containerId: string, containerName: string) => void
  closeTab: (tabId: string) => void
  setActive: (tabId: string | null) => void
}

export const useTerminalStore = create<TerminalStore>((set, get) => ({
  tabs: [],
  activeTabId: null,

  openTerminal: (containerId, containerName) => {
    const existing = get().tabs.find((t) => t.containerId === containerId)
    if (existing) {
      set({ activeTabId: existing.id })
      return
    }
    const id = `term-${containerId}-${Date.now()}`
    set((s) => ({
      tabs: [...s.tabs, { id, containerId, containerName }],
      activeTabId: id,
    }))
  },

  closeTab: (tabId) => set((s) => {
    const remaining = s.tabs.filter((t) => t.id !== tabId)
    return {
      tabs: remaining,
      activeTabId: s.activeTabId === tabId
        ? (remaining.length > 0 ? remaining[remaining.length - 1].id : null)
        : s.activeTabId,
    }
  }),

  setActive: (tabId) => set({ activeTabId: tabId }),
}))
