import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ChevronRight, FolderPlus, MoreVertical, Pencil, Plus, Trash2 } from "lucide-react"
import { useProjectStore } from "@/stores/project"
import { useToast } from "@/components/ui/Toast"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { cn } from "@/lib/utils"
import { CreateProjectDialog } from "./CreateProjectDialog"
import type { Project, Session } from "@/types"

/**
 * Projects laid out flat, each with its sessions nested underneath.
 *
 * Projects are the durable thing here — a session is one conversation about a
 * project — so they read better as headings over their own sessions than as a
 * mode you switch the whole sidebar into. Every project keeps its `+`, so
 * starting work in one is a single click from anywhere in the list.
 */
const EXPANDED_KEY = "openbox.expandedProjects"

function readExpanded(): Set<string> {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

function writeExpanded(ids: Set<string>) {
  try {
    localStorage.setItem(EXPANDED_KEY, JSON.stringify([...ids]))
  } catch {
    /* private mode — expansion just won't survive a reload */
  }
}

const statusColors: Record<string, string> = {
  idle: "bg-[hsl(var(--muted-foreground))]/30",
  busy: "bg-[hsl(var(--success))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--success))]",
  finalizing: "bg-[hsl(var(--success))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--success))]",
  retry: "bg-[hsl(var(--accent))] shadow-[0_0_6px_hsl(var(--accent))]",
  error: "bg-[hsl(var(--destructive))] shadow-[0_0_6px_hsl(var(--destructive))]",
  compacting: "bg-[hsl(var(--primary))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--primary))]",
}

interface ProjectTreeProps {
  sessions: Session[]
  currentSessionId: string | null
  searchQuery: string
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onNewChat: (projectId: string) => void
}

export function ProjectTree({
  sessions, currentSessionId, searchQuery, onSelectSession, onDeleteSession, onNewChat,
}: ProjectTreeProps) {
  const projects = useProjectStore((s) => s.projects)
  const renameProject = useProjectStore((s) => s.renameProject)
  const deleteProject = useProjectStore((s) => s.deleteProject)
  const { addToast } = useToast()

  const [expanded, setExpanded] = useState<Set<string>>(readExpanded)
  const [createOpen, setCreateOpen] = useState(false)
  const [renaming, setRenaming] = useState<Project | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [deleting, setDeleting] = useState<Project | null>(null)

  const byProject = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    const map = new Map<string, Session[]>()
    for (const s of sessions) {
      if (q && !(s.title || "").toLowerCase().includes(q)) continue
      const key = s.project_id || ""
      const list = map.get(key)
      if (list) list.push(s)
      else map.set(key, [s])
    }
    return map
  }, [sessions, searchQuery])

  // A search should reveal what it matched rather than hiding it behind a
  // collapsed heading, so any project with a hit opens for the duration.
  const searching = searchQuery.trim().length > 0

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      writeExpanded(next)
      return next
    })
  }, [])

  // Whichever project holds the open session should be open too.
  useEffect(() => {
    if (!currentSessionId) return
    const active = sessions.find((s) => s.id === currentSessionId)
    if (!active?.project_id) return
    setExpanded((prev) => {
      if (prev.has(active.project_id!)) return prev
      const next = new Set(prev).add(active.project_id!)
      writeExpanded(next)
      return next
    })
  }, [currentSessionId, sessions])

  const submitRename = useCallback(async () => {
    if (!renaming) return
    const name = renameValue.trim()
    if (!name || name === renaming.name) return setRenaming(null)
    try {
      await renameProject(renaming.id, name)
      addToast("success", `Renamed to ${name}`)
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Rename failed")
    }
    setRenaming(null)
  }, [renaming, renameValue, renameProject, addToast])

  const confirmDelete = useCallback(async () => {
    if (!deleting) return
    const target = deleting
    setDeleting(null)
    try {
      await deleteProject(target.id)
      addToast("success", `Deleted ${target.name} — files moved to trash`)
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Delete failed")
    }
  }, [deleting, deleteProject, addToast])

  // Sessions whose project has gone missing would otherwise be unreachable.
  const orphans = useMemo(() => {
    const known = new Set(projects.map((p) => p.id))
    return [...byProject.entries()]
      .filter(([pid]) => !known.has(pid))
      .flatMap(([, list]) => list)
  }, [byProject, projects])

  return (
    <div className="flex-1 overflow-y-auto pb-2">
      {projects.map((project) => {
        const list = byProject.get(project.id) ?? []
        const isOpen = expanded.has(project.id) || (searching && list.length > 0)
        return (
          <div key={project.id} className="mb-0.5">
            <ProjectHeader
              project={project}
              open={isOpen}
              count={list.length}
              onToggle={() => toggle(project.id)}
              onNewChat={() => onNewChat(project.id)}
              onRename={() => { setRenameValue(project.name); setRenaming(project) }}
              onDelete={project.slug === "default" ? undefined : () => setDeleting(project)}
            />
            {isOpen && (
              <div className="pl-2">
                {list.length === 0 ? (
                  <button
                    onClick={() => onNewChat(project.id)}
                    className="w-full text-left pl-6 pr-3 py-2 text-[11px] font-mono text-[hsl(var(--muted-foreground))]/60 hover:text-[hsl(var(--primary))] transition-colors cursor-pointer"
                  >
                    No sessions — start one
                  </button>
                ) : (
                  list.map((session) => (
                    <SessionRow
                      key={session.id}
                      session={session}
                      active={session.id === currentSessionId}
                      onSelect={() => onSelectSession(session.id)}
                      onDelete={() => onDeleteSession(session.id)}
                    />
                  ))
                )}
              </div>
            )}
          </div>
        )
      })}

      {orphans.length > 0 && (
        <div className="mb-0.5">
          <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]/60">
            Unfiled
          </div>
          <div className="pl-2">
            {orphans.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                active={session.id === currentSessionId}
                onSelect={() => onSelectSession(session.id)}
                onDelete={() => onDeleteSession(session.id)}
              />
            ))}
          </div>
        </div>
      )}

      {searching && byProject.size === 0 && (
        <div className="px-3 py-8 text-center text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
          No sessions found
        </div>
      )}

      <button
        onClick={() => setCreateOpen(true)}
        className="mt-1 w-full flex items-center gap-2 px-3 py-2.5 text-xs font-display font-medium text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--muted))]/40 transition-colors cursor-pointer"
      >
        <FolderPlus className="h-3.5 w-3.5" />
        New project
      </button>

      <CreateProjectDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(p) => {
          setExpanded((prev) => {
            const next = new Set(prev).add(p.id)
            writeExpanded(next)
            return next
          })
          addToast("success", `Created ${p.name} at ${p.directory}`)
        }}
      />

      {renaming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[hsl(var(--background))]/80 backdrop-blur-sm" onClick={() => setRenaming(null)} />
          <div className="relative w-full sm:w-[380px] bg-[hsl(var(--card))] rounded-sm border border-[hsl(var(--primary))]/20 shadow-[0_0_30px_hsl(var(--primary)/0.1)] p-5 animate-slide-up">
            <h3 className="text-sm font-display font-semibold mb-1">Rename project</h3>
            <p className="text-[11px] font-mono text-[hsl(var(--muted-foreground))]/70 mb-3">
              The folder stays <span className="text-[hsl(var(--foreground))]">{renaming.slug}</span> — renaming it
              would break paths the agent has already used.
            </p>
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitRename()
                if (e.key === "Escape") setRenaming(null)
              }}
              className="w-full px-3 py-2 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setRenaming(null)} className="px-3 py-1.5 text-xs font-mono rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer">
                Cancel
              </button>
              <button onClick={submitRename} className="px-3 py-1.5 text-xs font-mono rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleting !== null}
        title={`Delete ${deleting?.name ?? ""}?`}
        message={
          `Its sessions stay in your history, and the files in ${deleting?.directory ?? ""} ` +
          `move to the workspace trash rather than being erased.`
        }
        confirmLabel="Delete project"
        variant="danger"
        onConfirm={confirmDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  )
}

function ProjectHeader({
  project, open, count, onToggle, onNewChat, onRename, onDelete,
}: {
  project: Project
  open: boolean
  count: number
  onToggle: () => void
  onNewChat: () => void
  onRename: () => void
  onDelete?: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuOpen(false) }
    document.addEventListener("mousedown", onClick)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onClick)
      document.removeEventListener("keydown", onKey)
    }
  }, [menuOpen])

  return (
    <div className="group relative flex items-center gap-1 pr-1.5">
      <button
        onClick={onToggle}
        title={project.directory}
        aria-expanded={open}
        className="flex-1 min-w-0 flex items-center gap-1.5 px-2 py-2 rounded-sm hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
      >
        <ChevronRight className={cn(
          "h-3.5 w-3.5 shrink-0 text-[hsl(var(--muted-foreground))] transition-transform",
          open && "rotate-90",
        )} />
        <span className="text-sm font-display font-semibold text-[hsl(var(--foreground))] truncate">
          {project.name}
        </span>
        {!open && count > 0 && (
          <span className="ml-auto shrink-0 text-[10px] font-mono tabular-nums text-[hsl(var(--muted-foreground))]/60">
            {count}
          </span>
        )}
      </button>

      <button
        onClick={onNewChat}
        title={`New session in ${project.name}`}
        aria-label={`New session in ${project.name}`}
        className="shrink-0 p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>

      <div ref={menuRef} className="shrink-0 relative">
        <button
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={`${project.name} options`}
          className={cn(
            "p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer",
            menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus:opacity-100",
          )}
        >
          <MoreVertical className="h-3.5 w-3.5" />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full mt-1 z-30 w-40 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[0_0_20px_hsl(var(--primary)/0.1)] overflow-hidden animate-slide-up">
            <div className="px-3 py-2 border-b border-[hsl(var(--border))]">
              <div className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]/70 truncate">
                {project.directory}
              </div>
            </div>
            <button
              onClick={() => { setMenuOpen(false); onRename() }}
              className="w-full flex items-center gap-2 px-3 py-2 text-xs font-mono hover:bg-[hsl(var(--muted))]/60 transition-colors cursor-pointer text-left"
            >
              <Pencil className="h-3 w-3" /> Rename
            </button>
            {onDelete && (
              <button
                onClick={() => { setMenuOpen(false); onDelete() }}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-mono text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 transition-colors cursor-pointer text-left"
              >
                <Trash2 className="h-3 w-3" /> Delete
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function SessionRow({
  session, active, onSelect, onDelete,
}: {
  session: Session
  active: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect() }}
      className={cn(
        "group/session flex items-center gap-2 pl-4 pr-2 py-2 rounded-sm cursor-pointer transition-all",
        active
          ? "bg-[hsl(var(--primary))]/8 text-[hsl(var(--foreground))]"
          : "hover:bg-[hsl(var(--muted))]/50",
      )}
    >
      <span className={cn(
        "h-1.5 w-1.5 rounded-sm shrink-0",
        statusColors[session.status] || statusColors.idle,
      )} />
      <span className={cn(
        "flex-1 min-w-0 truncate text-[13px]",
        active
          ? "font-display font-medium text-[hsl(var(--foreground))]"
          : "text-[hsl(var(--muted-foreground))]",
      )}>
        {session.title || "New Chat"}
      </span>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete() }}
        aria-label="Delete session"
        className="shrink-0 opacity-0 group-hover/session:opacity-100 p-1 rounded-sm hover:bg-[hsl(var(--destructive))]/10 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))] transition-all cursor-pointer"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  )
}
