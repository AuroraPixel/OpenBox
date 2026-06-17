import { create } from "zustand"
import { persist } from "zustand/middleware"

type Theme = "light" | "dark" | "system"

interface UIStore {
  sidebarOpen: boolean
  rightPanelOpen: boolean
  bottomPanelOpen: boolean
  bottomPanelHeight: number
  theme: Theme
  commandPaletteOpen: boolean
  wsConnected: boolean
  pendingModel: string | null
  pendingAgent: string | null
  pendingVariant: string | null
  sandboxAvailable: boolean | null
  sandboxDialogOpen: boolean
  sandboxDialogCallback: (() => void) | null
  sandboxDialogAutoCreate: boolean  // Deprecated: always auto-creates now

  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleRightPanel: () => void
  setRightPanelOpen: (open: boolean) => void
  toggleBottomPanel: () => void
  setBottomPanelOpen: (open: boolean) => void
  setBottomPanelHeight: (h: number) => void
  setTheme: (t: Theme) => void
  setCommandPaletteOpen: (open: boolean) => void
  setWsConnected: (connected: boolean) => void
  setPendingModel: (model: string | null) => void
  setPendingAgent: (agent: string | null) => void
  setPendingVariant: (variant: string | null) => void
  setSandboxAvailable: (available: boolean | null) => void
  openSandboxDialog: (callback?: () => void, autoCreate?: boolean) => void
  closeSandboxDialog: () => void
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      rightPanelOpen: true,
      bottomPanelOpen: false,
      bottomPanelHeight: 250,
      theme: "dark",
      commandPaletteOpen: false,
      wsConnected: false,
      pendingModel: null,
      pendingAgent: null,
      pendingVariant: null,
      sandboxAvailable: null,
      sandboxDialogOpen: false,
      sandboxDialogCallback: null,
      sandboxDialogAutoCreate: false,

      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
      setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
      toggleBottomPanel: () => set((s) => ({ bottomPanelOpen: !s.bottomPanelOpen })),
      setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),
      setBottomPanelHeight: (h) => set({ bottomPanelHeight: Math.max(100, Math.min(600, h)) }),
      setTheme: (t) => {
        set({ theme: t })
        applyThemeToDocument(t)
      },
      setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
      setWsConnected: (connected) => set({ wsConnected: connected }),
      setPendingModel: (model) => set({ pendingModel: model }),
      setPendingAgent: (agent) => set({ pendingAgent: agent }),
      setPendingVariant: (variant) => set({ pendingVariant: variant }),
      setSandboxAvailable: (available) => set({ sandboxAvailable: available }),
      openSandboxDialog: (callback, autoCreate) => set({ sandboxDialogOpen: true, sandboxDialogCallback: callback || null, sandboxDialogAutoCreate: autoCreate || false }),
      closeSandboxDialog: () => set({ sandboxDialogOpen: false, sandboxDialogCallback: null, sandboxDialogAutoCreate: false }),
    }),
    {
      name: "openagent-ui",
      partialize: (s) => ({
        sidebarOpen: s.sidebarOpen,
        rightPanelOpen: s.rightPanelOpen,
        bottomPanelHeight: s.bottomPanelHeight,
        theme: s.theme,
        pendingModel: s.pendingModel,
        pendingAgent: s.pendingAgent,
        pendingVariant: s.pendingVariant,
      }),
    },
  ),
)

// ── Theme application ──

function applyThemeToDocument(theme: Theme) {
  const root = document.documentElement
  if (theme === "system") {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
    root.classList.toggle("light", !prefersDark)
  } else {
    root.classList.toggle("light", theme === "light")
  }
}

// Apply theme on store initialization
applyThemeToDocument(useUIStore.getState().theme)

// Listen for system theme changes when using "system" mode
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  const { theme } = useUIStore.getState()
  if (theme === "system") {
    applyThemeToDocument("system")
  }
})

// ── Server preference sync ──

let syncTimer: ReturnType<typeof setTimeout> | null = null

async function syncPreferencesToServer() {
  try {
    const state = useUIStore.getState()
    const { useAuthStore } = await import("@/stores/auth")
    if (!useAuthStore.getState().isAuthenticated) return

    const prefs = {
      theme: state.theme,
      default_model: state.pendingModel,
      default_agent: state.pendingAgent,
      default_variant: state.pendingVariant,
      sidebar_open: state.sidebarOpen,
      right_panel_open: state.rightPanelOpen,
      bottom_panel_height: state.bottomPanelHeight,
    }
    await fetch(`${import.meta.env.VITE_API_URL || ""}/api/auth/me/preferences`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${useAuthStore.getState().accessToken}`,
      },
      body: JSON.stringify(prefs),
    })
  } catch { /* ignore sync failures */ }
}

// Debounced sync: subscribe to preference-relevant state changes
useUIStore.subscribe((state, prevState) => {
  const changed =
    state.theme !== prevState.theme ||
    state.pendingModel !== prevState.pendingModel ||
    state.pendingAgent !== prevState.pendingAgent ||
    state.pendingVariant !== prevState.pendingVariant ||
    state.sidebarOpen !== prevState.sidebarOpen ||
    state.rightPanelOpen !== prevState.rightPanelOpen ||
    state.bottomPanelHeight !== prevState.bottomPanelHeight

  if (changed) {
    if (syncTimer) clearTimeout(syncTimer)
    syncTimer = setTimeout(syncPreferencesToServer, 1000)
  }
})

export async function loadPreferencesFromServer() {
  try {
    const { useAuthStore } = await import("@/stores/auth")
    const token = useAuthStore.getState().accessToken
    if (!token) return

    const resp = await fetch(`${import.meta.env.VITE_API_URL || ""}/api/auth/me/preferences`, {
      headers: { "Authorization": `Bearer ${token}` },
    })
    if (!resp.ok) return
    const prefs = await resp.json()
    if (prefs && typeof prefs === "object" && Object.keys(prefs).length > 0) {
      const store = useUIStore.getState()
      if (prefs.theme) store.setTheme(prefs.theme)
      if (prefs.default_model) store.setPendingModel(prefs.default_model)
      if (prefs.default_agent) store.setPendingAgent(prefs.default_agent)
      if (prefs.sidebar_open !== undefined) store.setSidebarOpen(prefs.sidebar_open)
      if (prefs.right_panel_open !== undefined) store.setRightPanelOpen(prefs.right_panel_open)
      if (prefs.bottom_panel_height) store.setBottomPanelHeight(prefs.bottom_panel_height)
    }
  } catch { /* ignore */ }
}
