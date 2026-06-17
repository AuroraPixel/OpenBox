import { useState, useCallback, useEffect, useMemo, useRef, lazy, Suspense } from "react"
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { StatusBar } from "@/components/layout/StatusBar"
import { Sidebar } from "@/components/layout/Sidebar"
import { RightPanel } from "@/components/layout/RightPanel"
import { BottomPanel } from "@/components/layout/BottomPanel"
import { CommandPalette } from "@/components/layout/CommandPalette"
import { SessionTabBar } from "@/components/layout/SessionTabBar"
import { ChatView } from "@/components/chat/ChatView"
import { WelcomePage } from "@/pages/WelcomePage"
import { ToastProvider } from "@/components/ui/Toast"
import { SandboxRequiredDialog } from "@/components/sandbox/SandboxRequiredDialog"
import { useWS } from "@/hooks/useWS"
import { useAuthStore, refreshAccessToken } from "@/stores/auth"
import { LandingPage } from "@/pages/LandingPage"
import { LoginPage } from "@/pages/LoginPage"
import { useKeyboard } from "@/hooks/useKeyboard"
import { useSessionStore } from "@/stores/session"
import { usePermissionStore } from "@/stores/permission"
import { useQuestionStore } from "@/stores/question"
import { useTerminalStore } from "@/stores/terminal"
import { useUIStore, loadPreferencesFromServer } from "@/stores/ui"
import { api } from "@/services/api"
import type { ContainerInfo } from "@/types"

const DiffView = lazy(() => import("@/components/diff/DiffView").then((m) => ({ default: m.DiffView })))
const PreviewPanel = lazy(() => import("@/components/preview/PreviewPanel").then((m) => ({ default: m.PreviewPanel })))
const DevBrowserPanel = lazy(() => import("@/components/browser/DevBrowserPanel").then((m) => ({ default: m.DevBrowserPanel })))
const FileBrowser = lazy(() => import("@/components/files/FileBrowser").then((m) => ({ default: m.FileBrowser })))
const SandboxPage = lazy(() => import("@/pages/SandboxPage").then((m) => ({ default: m.SandboxPage })))
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })))
const BrowserUseGuidePage = lazy(() => import("@/pages/BrowserUseGuidePage").then((m) => ({ default: m.BrowserUseGuidePage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthGate />
      </ToastProvider>
    </QueryClientProvider>
  )
}

type PublicRoute = "landing" | "login"

function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  const authUserId = useAuthStore((s) => s.user?.id || null)
  const lastUserIdRef = useRef<string | null>(null)
  const [publicRoute, setPublicRoute] = useState<PublicRoute>("landing")

  // Try to refresh token on mount
  useEffect(() => {
    refreshAccessToken()
  }, [])

  useEffect(() => {
    const last = lastUserIdRef.current
    if (!isAuthenticated) {
      useSessionStore.getState().reset()
      usePermissionStore.getState().clearAll()
      useQuestionStore.getState().clearAll()
      queryClient.removeQueries()
      return
    }
    if (last && authUserId && last !== authUserId) {
      useSessionStore.getState().reset()
      usePermissionStore.getState().clearAll()
      useQuestionStore.getState().clearAll()
      queryClient.removeQueries()
    }
    lastUserIdRef.current = authUserId
  }, [authUserId, isAuthenticated])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[hsl(var(--background))] grid-pattern">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 border-2 border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/10 flex items-center justify-center animate-glow-pulse">
            <div className="h-3 w-3 bg-[hsl(var(--primary))]" />
          </div>
          <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider">Loading...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    if (publicRoute === "login") {
      return <LoginPage onBack={() => setPublicRoute("landing")} />
    }
    return <LandingPage onLogin={() => setPublicRoute("login")} />
  }

  return <AppInner />
}

type Route =
  | { type: "welcome" }
  | { type: "session"; id: string }
  | { type: "session-terminal"; id: string }
  | { type: "session-files"; id: string }
  | { type: "session-diff"; id: string }
  | { type: "session-preview"; id: string }
  | { type: "session-browser"; id: string }
  | { type: "sandbox" }
  | { type: "settings"; sub?: string }
  | { type: "browser-use-guide" }

function AppInner() {
  useWS()
  useKeyboard()
  const authUserId = useAuthStore((s) => s.user?.id || null)

  // Load preferences from server once on mount (user is authenticated at this point)
  useEffect(() => {
    loadPreferencesFromServer()
  }, [])

  // Parse route from URL hash on mount (e.g. #/session/xxx)
  const parseHash = useCallback((): Route => {
    const hash = window.location.hash.replace(/^#/, "")
    if (hash.startsWith("/session/")) {
      const parts = hash.split("/")
      const id = parts[2]
      const sub = parts[3]
      if (sub === "terminal") return { type: "session-terminal", id }
      if (sub === "files") return { type: "session-files", id }
      if (sub === "diff") return { type: "session-diff", id }
      if (sub === "preview") return { type: "session-preview", id }
      if (sub === "browser") return { type: "session-browser", id }
      return { type: "session", id }
    }
    if (hash === "/sandbox") return { type: "sandbox" }
    if (hash === "/browser-use-guide") return { type: "browser-use-guide" }
    if (hash.startsWith("/settings")) return { type: "settings", sub: hash.split("/")[2] }
    return { type: "welcome" }
  }, [])

  const [route, setRoute] = useState<Route>(parseHash)
  const switchSession = useSessionStore((s) => s.switchSession)

  // Restore session on mount from hash
  useEffect(() => {
    const r = parseHash()
    if ("id" in r && r.id) switchSession(r.id)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const setSessions = useSessionStore((s) => s.setSessions)
  const openTerminal = useTerminalStore((s) => s.openTerminal)
  const setBottomPanelOpen = useUIStore((s) => s.setBottomPanelOpen)

  // Fetch containers
  const { data: containerData } = useQuery({
    queryKey: ["containers", authUserId],
    queryFn: api.listContainers,
    refetchInterval: 30000,
  })
  const containers: ContainerInfo[] = useMemo(() => containerData?.containers || [], [containerData])

  // Fetch session list from backend and populate store
  const { data: sessionList } = useQuery({
    queryKey: ["sessions", authUserId],
    queryFn: api.listSessions,
    staleTime: 30000,
  })

  useEffect(() => {
    setSessions(sessionList || [])
  }, [sessionList, setSessions])

  // Sandbox dialog state
  const [showCreateSandbox, setShowCreateSandbox] = useState(false)

  const handleNavigate = useCallback((path: string) => {
    // Sync route to URL hash so refresh preserves the current view
    window.location.hash = path === "/" ? "" : path

    if (path === "/" || path === "") {
      setRoute({ type: "welcome" })
      switchSession(null)
    } else if (path.startsWith("/session/")) {
      const parts = path.split("/")
      const id = parts[2]
      const sub = parts[3]
      switchSession(id)
      if (sub === "terminal") setRoute({ type: "session-terminal", id })
      else if (sub === "files") setRoute({ type: "session-files", id })
      else if (sub === "diff") setRoute({ type: "session-diff", id })
      else if (sub === "preview") setRoute({ type: "session-preview", id })
      else if (sub === "browser") setRoute({ type: "session-browser", id })
      else setRoute({ type: "session", id })
    } else if (path === "/sandbox") {
      setRoute({ type: "sandbox" })
    } else if (path === "/browser-use-guide") {
      setRoute({ type: "browser-use-guide" })
    } else if (path.startsWith("/settings")) {
      const sub = path.split("/")[2]
      setRoute({ type: "settings", sub })
    }
  }, [switchSession])

  const handleTerminal = useCallback((containerId: string) => {
    const container = containers.find((c) => c.id === containerId)
    if (!container) return
    openTerminal(containerId, container.name)
    setBottomPanelOpen(true)
  }, [containers, openTerminal, setBottomPanelOpen])

  // Determine if we're in a session view
  const sessionId = route.type.startsWith("session") && "id" in route ? (route as { id: string }).id : null
  const activeSessionTab = route.type === "session-terminal" ? "terminal" as const
    : route.type === "session-files" ? "files" as const
    : route.type === "session-diff" ? "diff" as const
    : route.type === "session-preview" ? "preview" as const
    : route.type === "session-browser" ? "browser" as const
    : "chat" as const

  const handleSessionTab = useCallback((tab: "chat" | "terminal" | "files" | "diff" | "preview" | "browser") => {
    if (!sessionId) return
    if (tab === "chat") handleNavigate(`/session/${sessionId}`)
    else handleNavigate(`/session/${sessionId}/${tab}`)
  }, [sessionId, handleNavigate])

  // Auto-open terminal panel when switching to terminal tab
  useEffect(() => {
    if (route.type === "session-terminal") {
      const runningContainer = containers.find((c) => c.status === "running")
      if (runningContainer) {
        handleTerminal(runningContainer.id)
      }
    }
  }, [route.type, containers, handleTerminal])

  // Render main content based on route
  const renderMain = () => {
    switch (route.type) {
      case "welcome":
        return <WelcomePage onNavigate={handleNavigate} />
      case "session":
      case "session-terminal":
        return <ChatView sessionId={(route as { id: string }).id} onNavigate={handleNavigate} />
      case "session-files": {
        const firstContainer = containers.find((c) => c.status === "running") || containers[0]
        return <FileBrowser containerId={firstContainer?.id} />
      }
      case "session-diff":
        return <DiffView sessionId={(route as { id: string }).id} />
      case "session-preview":
        return <PreviewPanel sessionId={(route as { id: string }).id} />
      case "session-browser":
        return <DevBrowserPanel sessionId={(route as { id: string }).id} />
      case "sandbox":
        return (
          <SandboxPage
            containers={containers}
            onTerminal={handleTerminal}
            showCreate={showCreateSandbox}
            onShowCreate={setShowCreateSandbox}
          />
        )
      case "browser-use-guide":
        return <BrowserUseGuidePage />
      case "settings":
        return <SettingsPage sub={route.sub} />
      default:
        return <WelcomePage onNavigate={handleNavigate} />
    }
  }

  // Full-screen routes rendered outside the shell
  if (route.type === "browser-use-guide") {
    return (
      <Suspense fallback={<div className="h-screen flex items-center justify-center">Loading...</div>}>
        <BrowserUseGuidePage />
      </Suspense>
    )
  }

  return (
    <div className="h-screen flex flex-col">
      <StatusBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          containers={containers}
          onTerminal={handleTerminal}
          onCreateSandbox={() => setShowCreateSandbox(true)}
          onNavigate={handleNavigate}
        />
        <main className="flex-1 flex flex-col overflow-hidden">
          {sessionId && (
            <SessionTabBar sessionId={sessionId} activeTab={activeSessionTab} onTabChange={handleSessionTab} />
          )}
          <div className="flex-1 flex overflow-hidden">
            <div className="flex-1 overflow-hidden">
              <Suspense
                fallback={
                  <div className="h-full flex items-center justify-center text-sm text-[hsl(var(--muted-foreground))]">
                    Loading...
                  </div>
                }
              >
                {renderMain()}
              </Suspense>
            </div>
            <RightPanel />
          </div>
          <BottomPanel containers={containers} />
        </main>
      </div>
      <CommandPalette onNavigate={handleNavigate} />
      <SandboxRequiredDialog />
    </div>
  )
}
