import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Zap } from "lucide-react"
import { api } from "@/services/api"

const defaultCommands = [
  { name: "/review", description: "Review code changes" },
  { name: "/commit", description: "Create a git commit" },
  { name: "/init", description: "Initialize project" },
  { name: "/compact", description: "Compact context" },
  { name: "/help", description: "Show available commands" },
]

interface SlashCommandProps {
  onSelect: (command: string) => void
  onClose: () => void
  filter: string
}

export function SlashCommand({ onSelect, filter }: SlashCommandProps) {
  // Fetch commands from API, fall back to defaults
  const { data: apiCommands } = useQuery({
    queryKey: ["commands"],
    queryFn: api.listCommands,
    staleTime: 60000,
  })

  const commands = useMemo(() => {
    if (apiCommands && apiCommands.length > 0) {
      return apiCommands.map((c) => ({ name: `/${c.name}`, description: c.description }))
    }
    return defaultCommands
  }, [apiCommands])

  const filtered = useMemo(() => {
    if (!filter) return commands
    const q = filter.toLowerCase()
    return commands.filter((cmd) =>
      cmd.name.toLowerCase().includes(q) || cmd.description.toLowerCase().includes(q),
    )
  }, [filter, commands])

  if (filtered.length === 0) return null

  return (
    <div className="absolute bottom-full left-0 mb-2 w-72 rounded-sm border border-[hsl(var(--primary))]/20 bg-[hsl(var(--card))] shadow-[0_0_16px_hsl(var(--primary)/0.1)] py-1.5 z-10 animate-fade-in">
      {filtered.map((cmd) => (
        <button
          key={cmd.name}
          onClick={() => onSelect(cmd.name)}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-[hsl(var(--primary))]/10 transition-colors cursor-pointer"
        >
          <Zap className="h-3.5 w-3.5 text-[hsl(var(--accent))] glow-amber" />
          <span className="font-mono text-xs font-medium text-[hsl(var(--primary))]">{cmd.name}</span>
          <span className="text-[hsl(var(--muted-foreground))] text-xs ml-auto font-mono uppercase tracking-wider">{cmd.description}</span>
        </button>
      ))}
    </div>
  )
}
