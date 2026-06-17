import { useState, useCallback, useMemo } from "react"
import { Plus, Search, MessageSquare, Box, ChevronRight, Settings, X, LogOut } from "lucide-react"
import { useSessionStore } from "@/stores/session"
import { useUIStore } from "@/stores/ui"
import { SessionList } from "@/components/chat/SessionList"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/stores/auth"
import { useToast } from "@/components/ui/Toast"
import type { ContainerInfo } from "@/types"

interface SidebarProps {
  containers: ContainerInfo[]
  onTerminal: (id: string) => void
  onCreateSandbox: () => void
  onNavigate: (path: string) => void
}

export function Sidebar({ containers, onTerminal, onCreateSandbox, onNavigate }: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const [sandboxExpanded, setSandboxExpanded] = useState(false)
  const { addToast } = useToast()
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const sessions = useSessionStore((s) => s.sessions)
  const removeSession = useSessionStore((s) => s.removeSession)

  const handleNewChat = useCallback(async () => {
    try {
      const realId = await useSessionStore.getState().ensureRealSession()
      onNavigate(`/session/${realId}`)
      setSidebarOpen(false) // close on mobile
    } catch {
      addToast("error", "Failed to create a new chat session.")
    }
  }, [onNavigate, setSidebarOpen, addToast])

  const handleDeleteSession = useCallback(async (id: string) => {
    removeSession(id)
    if (currentSessionId === id) {
      onNavigate("/")
    }
    try {
      await api.deleteSession(id)
    } catch {
      // Session already removed from UI optimistically
    }
  }, [removeSession, currentSessionId, onNavigate])

  const handleSelectSession = useCallback((id: string) => {
    onNavigate(`/session/${id}`)
    setSidebarOpen(false) // close on mobile
  }, [onNavigate, setSidebarOpen])

  const handleNavigateAndClose = useCallback((path: string) => {
    onNavigate(path)
    setSidebarOpen(false)
  }, [onNavigate, setSidebarOpen])

  const runningContainers = useMemo(() => containers.filter((c) => c.status === "running"), [containers])

  if (!sidebarOpen) return null

  const sidebarContent = (
    <aside className="w-64 sm:w-64 border-r border-[hsl(var(--border))] bg-[hsl(var(--sidebar))] flex flex-col h-full shrink-0">
      {/* Mobile close button */}
      <div className="sm:hidden flex items-center justify-between px-3 pt-3 pb-1">
        <span className="text-sm font-display font-semibold text-[hsl(var(--foreground))]">Menu</span>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-2 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))]"
          aria-label="Close sidebar"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* New Chat button */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-3 py-3 sm:py-2.5 rounded-sm text-sm font-display font-medium transition-all cursor-pointer",
            "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
            "hover:opacity-90 shadow-[0_0_12px_hsl(var(--primary)/0.3)] animate-glow-pulse",
          )}
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sessions..."
            className="w-full pl-8 pr-3 py-2 sm:py-1.5 text-sm sm:text-xs font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-1 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/20 transition-all"
          />
        </div>
      </div>

      {/* Sessions section */}
      <div className="flex-1 overflow-y-auto">
        <div className="px-3 py-1.5">
          <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1">
            <MessageSquare className="h-3 w-3" />
            Sessions
          </div>
        </div>
        <SessionList
          sessions={sessions}
          currentSessionId={currentSessionId}
          searchQuery={searchQuery}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
        />
      </div>

      <div className="border-t border-[hsl(var(--border))]" />

      {/* Sandbox section (collapsible) */}
      <div className="border-t border-[hsl(var(--border))]">
        <button
          onClick={() => setSandboxExpanded(!sandboxExpanded)}
          className="w-full flex items-center gap-1.5 px-3 py-3 sm:py-2.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
        >
          <span className={cn("transition-transform", sandboxExpanded && "rotate-90")}>
            <ChevronRight className="h-3 w-3" />
          </span>
          <Box className="h-3 w-3" />
          Sandboxes
          {runningContainers.length > 0 && (
            <span className="ml-auto flex items-center gap-1 text-[hsl(var(--success))]">
              <span className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--success))] shadow-[0_0_6px_hsl(var(--success)/0.5)] animate-pulse-dot" />
              {runningContainers.length}
            </span>
          )}
        </button>
        {sandboxExpanded && (
          <div className="px-2 pb-2 space-y-0.5">
            {containers.length === 0 && (
              <div className="px-2 py-3 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] text-center grid-pattern">
                No sandboxes running
              </div>
            )}
            {containers.slice(0, 5).map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-2 px-2.5 py-2 sm:py-1.5 rounded-sm text-xs font-mono hover:bg-[hsl(var(--muted))]/60 cursor-pointer transition-colors"
                onClick={() => c.status === "running" && onTerminal(c.id)}
              >
                <div className={cn(
                  "h-1.5 w-1.5 rounded-full shrink-0",
                  c.status === "running" ? "bg-[hsl(var(--success))] shadow-[0_0_6px_hsl(var(--success)/0.4)]" : "bg-[hsl(var(--muted-foreground))]/40",
                )} />
                <span className="truncate flex-1 text-[hsl(var(--foreground))]">{c.name}</span>
              </div>
            ))}
            <button
              onClick={onCreateSandbox}
              className="w-full text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] py-2 sm:py-1.5 cursor-pointer transition-colors"
            >
              + New Sandbox
            </button>
            <button
              onClick={() => handleNavigateAndClose("/sandbox")}
              className="w-full text-xs font-mono uppercase tracking-wider text-[hsl(var(--primary))] py-1 cursor-pointer hover:underline glow-cyan"
            >
              Manage All
            </button>
          </div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="border-t border-[hsl(var(--border))] p-2">
        <button
          onClick={() => handleNavigateAndClose("/settings")}
          className="w-full flex items-center gap-2 px-3 py-2.5 sm:py-2 rounded-sm text-xs font-mono text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 hover:text-[hsl(var(--foreground))] transition-colors cursor-pointer"
        >
          <Settings className="h-3.5 w-3.5" />
          Settings
        </button>
        <button
          onClick={() => useAuthStore.getState().clearAuth()}
          className="w-full flex items-center gap-2 px-3 py-2.5 sm:py-2 rounded-sm text-xs font-mono text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 hover:text-[hsl(var(--destructive))] transition-colors cursor-pointer"
        >
          <LogOut className="h-3.5 w-3.5" />
          Logout
        </button>
      </div>
    </aside>
  )

  return (
    <>
      {/* Desktop: inline sidebar */}
      <div className="hidden sm:block">{sidebarContent}</div>

      {/* Mobile: overlay sidebar with backdrop */}
      <div className="sm:hidden fixed inset-0 z-50 flex">
        <div
          className="absolute inset-0 bg-[hsl(var(--background))]/60 backdrop-blur-sm"
          onClick={() => setSidebarOpen(false)}
        />
        <div className="relative animate-fade-in">
          {sidebarContent}
        </div>
      </div>
    </>
  )
}
