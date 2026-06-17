import { useState } from "react"
import { Info, ListTodo, FileText, X } from "lucide-react"
import { useUIStore } from "@/stores/ui"
import { useSessionStore } from "@/stores/session"
import { TodoPanel } from "@/components/todo/TodoPanel"
import { ContextPanel } from "@/components/context/ContextPanel"
import { CronJobList } from "@/components/cron/CronJobList"
import { cn } from "@/lib/utils"

type Tab = "context" | "todo" | "details"

export function RightPanel() {
  const rightPanelOpen = useUIStore((s) => s.rightPanelOpen)
  const setRightPanelOpen = useUIStore((s) => s.setRightPanelOpen)
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const sessions = useSessionStore((s) => s.sessions)

  const [activeTab, setActiveTab] = useState<Tab>("context")

  if (!rightPanelOpen) return null

  const currentSession = sessions.find((s) => s.id === currentSessionId)

  const tabs: { id: Tab; label: string; icon: typeof Info }[] = [
    { id: "context", label: "Context", icon: Info },
    { id: "todo", label: "Todo", icon: ListTodo },
    { id: "details", label: "Details", icon: FileText },
  ]

  const panelContent = (
    <>
      {/* Header */}
      <div className="flex items-center gap-1 px-2 h-10 border-b border-[hsl(var(--border))] shrink-0">
        {tabs.map((tab) => {
          const Icon = tab.icon
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
                activeTab === tab.id
                  ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] shadow-[0_0_8px_hsl(var(--primary)/0.15)] border border-[hsl(var(--primary))]/20"
                  : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]/60"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          )
        })}
        {/* Mobile close button */}
        <button
          onClick={() => setRightPanelOpen(false)}
          className="lg:hidden ml-auto p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {!currentSessionId ? (
          <EmptyState message="Select a session to view details" />
        ) : (
          <>
            {activeTab === "context" && <ContextTabContent />}
            {activeTab === "todo" && <TodoTabContent sessionId={currentSessionId} />}
            {activeTab === "details" && <DetailsTabContent session={currentSession} />}
          </>
        )}
      </div>
    </>
  )

  return (
    <>
      {/* Desktop: inline sidebar */}
      <aside className="hidden lg:flex w-72 border-l border-[hsl(var(--border))] bg-[hsl(var(--card))] flex-col h-full shrink-0">
        {panelContent}
      </aside>

      {/* Mobile/Tablet: overlay drawer from right */}
      <div className="lg:hidden fixed inset-0 z-50 flex justify-end">
        <div
          className="absolute inset-0 bg-[hsl(var(--background))]/60 backdrop-blur-sm"
          onClick={() => setRightPanelOpen(false)}
        />
        <aside className="relative w-80 max-w-[85vw] bg-[hsl(var(--card))] border-l border-[hsl(var(--border))] flex flex-col h-full animate-slide-in-right">
          {panelContent}
        </aside>
      </div>
    </>
  )
}

function ContextTabContent() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === currentSessionId))
  const hasData = !!session?.token_usage

  if (!hasData) return <EmptyState message="No context usage data available" />
  return <ContextPanel />
}

function TodoTabContent({ sessionId }: { sessionId: string }) {
  return <TodoPanel sessionId={sessionId} fallbackEmpty />
}

function DetailsTabContent({ session }: { session?: import("@/types").Session }) {
  if (!session) {
    return <EmptyState message="Session not found" />
  }

  const details = [
    { label: "Session ID", value: session.id },
    { label: "Status", value: session.status },
    { label: "Agent", value: session.agent || "build" },
    { label: "Model", value: session.model?.split("/").pop() || "claude-sonnet" },
    { label: "Created", value: formatTime(session.created_at) },
    { label: "Updated", value: formatTime(session.updated_at) },
    ...(session.additions != null ? [{ label: "Additions", value: `+${session.additions}` }] : []),
    ...(session.deletions != null ? [{ label: "Deletions", value: `-${session.deletions}` }] : []),
    ...(session.files_changed != null ? [{ label: "Files Changed", value: `${session.files_changed}` }] : []),
  ]

  return (
    <div className="px-4 py-4 space-y-6">
      {/* Session Details */}
      <div>
        <h3 className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-3 glow-cyan">
          Session Details
        </h3>
        <div className="border-t border-[hsl(var(--border))] mb-3" />
        <div className="space-y-2.5">
          {details.map((d) => (
            <div key={d.label} className="flex items-center justify-between text-xs">
              <span className="text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider">{d.label}</span>
              <span className="font-mono text-[hsl(var(--foreground))] text-right max-w-[140px] truncate tabular-nums" title={d.value}>
                {d.value}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Scheduled Tasks */}
      <div>
        <div className="border-t border-[hsl(var(--border))] mb-4" />
        <CronJobList sessionId={session.id} compact />
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center grid-pattern">
      <div className="h-10 w-10 rounded-sm bg-[hsl(var(--muted))] border border-[hsl(var(--border))] flex items-center justify-center mb-3">
        <Info className="h-5 w-5 text-[hsl(var(--muted-foreground))]/50" />
      </div>
      <p className="text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">{message}</p>
    </div>
  )
}

function formatTime(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleString()
  } catch {
    return dateStr
  }
}
