import { useMemo } from "react"
import { Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Session } from "@/types"

interface SessionListProps {
  sessions: Session[]
  currentSessionId: string | null
  searchQuery: string
  onSelect: (id: string) => void
  onDelete?: (id: string) => void
}

const statusColors: Record<string, string> = {
  idle: "bg-[hsl(var(--muted-foreground))]/30",
  busy: "bg-[hsl(var(--success))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--success))]",
  finalizing: "bg-[hsl(var(--success))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--success))]",
  retry: "bg-[hsl(var(--accent))] shadow-[0_0_6px_hsl(var(--accent))]",
  error: "bg-[hsl(var(--destructive))] shadow-[0_0_6px_hsl(var(--destructive))]",
  compacting: "bg-[hsl(var(--primary))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--primary))]",
}

export function SessionList({ sessions, currentSessionId, searchQuery, onSelect, onDelete }: SessionListProps) {
  const filtered = useMemo(() => {
    if (!searchQuery) return sessions
    const q = searchQuery.toLowerCase()
    return sessions.filter((s) => s.title?.toLowerCase().includes(q))
  }, [sessions, searchQuery])

  if (filtered.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-xs text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider">
        {searchQuery ? "No sessions found" : "No sessions yet"}
      </div>
    )
  }

  return (
    <div className="px-2 space-y-0.5">
      {filtered.map((session) => (
        <div
          key={session.id}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(session.id)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(session.id) }}
          className={cn(
            "w-full text-left px-3 py-2.5 rounded-sm transition-all cursor-pointer group",
            currentSessionId === session.id
              ? "bg-[hsl(var(--primary))]/8 border border-[hsl(var(--primary))]/20 shadow-[0_0_8px_hsl(var(--primary)/0.1)]"
              : "hover:bg-[hsl(var(--muted))]/60 border border-transparent",
          )}
        >
          <div className="flex items-center gap-2 mb-0.5">
            <div className={cn("h-1.5 w-1.5 rounded-sm shrink-0", statusColors[session.status] || statusColors.idle)} />
            <span className="text-sm font-display font-medium truncate flex-1 text-[hsl(var(--foreground))]">
              {session.title || "New Chat"}
            </span>
            {onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(session.id)
                }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded-sm hover:bg-[hsl(var(--destructive))]/10 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))] transition-all cursor-pointer"
                aria-label="Delete session"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2 text-[10px] text-[hsl(var(--muted-foreground))] pl-3.5 font-mono">
            <span className="tabular-nums">{formatRelativeTime(session.updated_at)}</span>
            <span className="opacity-40">·</span>
            <span className="font-mono uppercase tracking-wider">{session.model?.split("/").pop() || "claude-sonnet"}</span>
          </div>
          {(session.additions || session.deletions) && (
            <div className="flex items-center gap-1.5 text-[10px] pl-3.5 mt-0.5 tabular-nums font-mono">
              {session.additions ? <span className="text-[hsl(var(--success))]">+{session.additions}</span> : null}
              {session.deletions ? <span className="text-[hsl(var(--destructive))]">-{session.deletions}</span> : null}
              {session.files_changed ? <span className="text-[hsl(var(--muted-foreground))]">{session.files_changed} files</span> : null}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function formatRelativeTime(dateStr: string): string {
  const now = Date.now()
  const date = new Date(dateStr).getTime()
  const diff = now - date
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
