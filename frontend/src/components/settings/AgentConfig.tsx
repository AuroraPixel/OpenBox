import { Bot, Cpu, Wrench } from "lucide-react"
import { Badge } from "@/components/ui/Badge"
import { cn } from "@/lib/utils"
import type { AgentConfig as AgentConfigType } from "@/types"

interface AgentConfigProps {
  agents: AgentConfigType[]
}

export function AgentConfig({ agents }: AgentConfigProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-display uppercase tracking-wider text-[hsl(var(--foreground))]">Agents</h2>
        <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
          {agents.length} configured
        </span>
      </div>

      <div className="grid gap-3">
        {agents.map((agent) => (
          <div
            key={agent.name}
            className={cn(
              "rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-5",
              "hover:border-[hsl(var(--primary))]/40 transition-colors",
            )}
          >
            {/* Header row */}
            <div className="flex items-center gap-3 mb-3">
              <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/10 flex items-center justify-center shrink-0 glow-cyan">
                <Bot className="h-4.5 w-4.5 text-[hsl(var(--primary))]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-display text-sm uppercase tracking-wider">{agent.name}</h3>
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <Cpu className="h-3 w-3 text-[hsl(var(--muted-foreground))]" />
                  <span className="text-xs text-[hsl(var(--muted-foreground))] font-mono">{agent.model}</span>
                </div>
              </div>
            </div>

            {/* Description */}
            <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4 leading-relaxed">
              {agent.description}
            </p>

            {/* Tools */}
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))] uppercase tracking-wider font-mono">
                <Wrench className="h-3 w-3" />
                <span>{agent.tools.length} tools available</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {agent.tools.slice(0, 12).map((tool) => (
                  <span
                    key={tool}
                    className="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-mono bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))]"
                  >
                    {tool}
                  </span>
                ))}
                {agent.tools.length > 12 && (
                  <Badge variant="default">+{agent.tools.length - 12} more</Badge>
                )}
              </div>
            </div>
          </div>
        ))}

        {agents.length === 0 && (
          <div className="rounded-sm border border-dashed border-[hsl(var(--border))] p-10 text-center grid-pattern">
            <Bot className="h-8 w-8 mx-auto mb-3 text-[hsl(var(--muted-foreground))]/40" />
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No agents configured</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1">Agents will appear here once configured by the system.</p>
          </div>
        )}
      </div>
    </div>
  )
}
