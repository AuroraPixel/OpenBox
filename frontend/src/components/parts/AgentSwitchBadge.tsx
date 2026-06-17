import { ArrowRightLeft } from "lucide-react"

interface AgentSwitchBadgeProps {
  agent: string
}

export function AgentSwitchBadge({ agent }: AgentSwitchBadgeProps) {
  return (
    <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-sm bg-[hsl(var(--card))] border border-[hsl(var(--border))]/50 text-xs text-[hsl(var(--muted-foreground))] shadow-[0_0_6px_hsl(var(--primary)/0.15)]">
      <div className="flex items-center justify-center h-5 w-5 rounded-sm bg-[hsl(var(--primary))]/10 shadow-[0_0_6px_hsl(var(--primary)/0.3)]">
        <ArrowRightLeft className="h-3 w-3 text-[hsl(var(--primary))] glow-cyan" />
      </div>
      <span className="font-mono uppercase tracking-wider">Switched to agent: <span className="font-mono font-medium text-[hsl(var(--primary))]">{agent}</span></span>
    </div>
  )
}
