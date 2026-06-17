import { useState, useEffect, useRef, useMemo } from "react"
import { Search, MessageSquare, Terminal, Settings, Plus, Zap } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { useUIStore } from "@/stores/ui"
import { useSessionStore } from "@/stores/session"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface PaletteItem {
  id: string
  label: string
  description?: string
  icon: React.ReactNode
  section: string
  action: () => void
}

interface CommandPaletteProps {
  onNavigate: (path: string) => void
}

export function CommandPalette({ onNavigate }: CommandPaletteProps) {
  const open = useUIStore((s) => s.commandPaletteOpen)
  const setOpen = useUIStore((s) => s.setCommandPaletteOpen)
  const sessions = useSessionStore((s) => s.sessions)
  const [query, setQuery] = useState("")
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Fetch commands from API
  const { data: apiCommands } = useQuery({
    queryKey: ["commands-palette"],
    queryFn: api.listCommands,
    staleTime: 60000,
  })

  const items = useMemo<PaletteItem[]>(() => {
    const list: PaletteItem[] = []

    // Actions
    list.push({
      id: "new-session",
      label: "New Session",
      icon: <Plus className="h-4 w-4" />,
      section: "Actions",
      action: () => { onNavigate("/"); setOpen(false) },
    })
    list.push({
      id: "settings",
      label: "Settings",
      icon: <Settings className="h-4 w-4" />,
      section: "Actions",
      action: () => { onNavigate("/settings"); setOpen(false) },
    })
    list.push({
      id: "sandboxes",
      label: "Manage Sandboxes",
      icon: <Terminal className="h-4 w-4" />,
      section: "Actions",
      action: () => { onNavigate("/sandbox"); setOpen(false) },
    })

    // Sessions
    sessions.slice(0, 10).forEach((s) => {
      list.push({
        id: `session-${s.id}`,
        label: s.title || "Untitled",
        description: new Date(s.updated_at).toLocaleDateString(),
        icon: <MessageSquare className="h-4 w-4" />,
        section: "Sessions",
        action: () => { onNavigate(`/session/${s.id}`); setOpen(false) },
      })
    })

    // Dynamic commands from API
    const commands = apiCommands || []
    commands.forEach((cmd) => {
      list.push({
        id: `cmd-${cmd.name}`,
        label: `/${cmd.name}`,
        description: cmd.description,
        icon: <Zap className="h-4 w-4" />,
        section: "Commands",
        action: () => { setOpen(false) },
      })
    })

    return list
  }, [sessions, apiCommands, onNavigate, setOpen])

  const filtered = useMemo(() => {
    if (!query) return items
    const q = query.toLowerCase()
    return items.filter((item) =>
      item.label.toLowerCase().includes(q) ||
      item.description?.toLowerCase().includes(q) ||
      item.section.toLowerCase().includes(q),
    )
  }, [items, query])

  useEffect(() => {
    if (open) {
      setQuery("")
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  if (!open) return null

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setSelectedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault()
      filtered[selectedIndex].action()
    } else if (e.key === "Escape") {
      setOpen(false)
    }
  }

  const sections = [...new Set(filtered.map((i) => i.section))]

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center pt-[18vh]">
      <div className="absolute inset-0 bg-[hsl(var(--background))]/80 backdrop-blur-sm scanlines" onClick={() => setOpen(false)} />
      <div className="relative w-[540px] bg-[hsl(var(--card))] rounded-sm border border-[hsl(var(--primary))]/20 shadow-[0_0_40px_hsl(var(--primary)/0.1)] overflow-hidden animate-slide-up">
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-[hsl(var(--border))]">
          <Search className="h-4 w-4 text-[hsl(var(--primary))] glow-cyan" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search..."
            className="flex-1 bg-transparent text-sm font-mono text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-0"
          />
          <kbd className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))] rounded-sm px-1.5 py-0.5">
            ESC
          </kbd>
        </div>
        <div className="max-h-[360px] overflow-y-auto py-1.5">
          {filtered.length === 0 && (
            <div className="px-4 py-10 text-center text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] grid-pattern">
              No results found
            </div>
          )}
          {sections.map((section) => {
            const sectionItems = filtered.filter((i) => i.section === section)
            return (
              <div key={section}>
                <div className="px-4 py-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] glow-cyan">
                  {section}
                </div>
                {sectionItems.map((item) => {
                  const idx = filtered.indexOf(item)
                  return (
                    <button
                      key={item.id}
                      onClick={item.action}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-2.5 text-sm font-mono transition-colors cursor-pointer mx-1.5 rounded-sm",
                        "w-[calc(100%-12px)]",
                        idx === selectedIndex
                          ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--foreground))] border border-[hsl(var(--primary))]/20 shadow-[0_0_8px_hsl(var(--primary)/0.1)]"
                          : "text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60",
                      )}
                    >
                      <span className="text-[hsl(var(--primary))]">{item.icon}</span>
                      <span className="flex-1 text-left truncate">{item.label}</span>
                      {item.description && (
                        <span className="text-[11px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]/70">{item.description}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
