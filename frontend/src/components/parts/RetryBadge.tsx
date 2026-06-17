import { RefreshCw } from "lucide-react"

interface RetryBadgeProps {
  attempt: number
  reason?: string
}

export function RetryBadge({ attempt, reason }: RetryBadgeProps) {
  return (
    <div className="flex items-center gap-2.5 px-3.5 py-2 rounded-sm bg-[hsl(var(--card))] border border-[hsl(var(--accent))]/20 text-xs text-[hsl(var(--accent))] shadow-[0_0_6px_hsl(var(--accent)/0.2)]">
      <div className="flex items-center justify-center h-5 w-5 rounded-sm bg-[hsl(var(--accent))]/10 shadow-[0_0_6px_hsl(var(--accent)/0.3)]">
        <RefreshCw className="h-3 w-3 animate-spin-slow glow-amber" />
      </div>
      <span className="font-mono uppercase tracking-wider tabular-nums">Retrying... attempt {attempt}</span>
      {reason && <span className="text-[hsl(var(--accent))]/50 font-mono">({reason})</span>}
    </div>
  )
}
