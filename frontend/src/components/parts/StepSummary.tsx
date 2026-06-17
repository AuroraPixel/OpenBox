import { Zap, Clock, DollarSign } from "lucide-react"

interface StepSummaryProps {
  inputTokens: number
  outputTokens: number
  cost: number
  duration: number
}

export function StepSummary({ inputTokens, outputTokens, cost, duration }: StepSummaryProps) {
  return (
    <div className="flex items-center gap-4 py-1.5 px-2.5 text-[10px] text-[hsl(var(--muted-foreground))]/70 border-t tabular-nums font-mono">
      <div className="flex items-center gap-1.5">
        <Zap className="h-3 w-3 text-[hsl(var(--accent))] opacity-60 glow-amber" />
        <span>{inputTokens.toLocaleString()} in / {outputTokens.toLocaleString()} out</span>
      </div>
      <div className="flex items-center gap-1.5">
        <DollarSign className="h-3 w-3 text-[hsl(var(--success))] opacity-60 glow-green" />
        <span>${cost.toFixed(4)}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Clock className="h-3 w-3 text-[hsl(var(--primary))] opacity-60 glow-cyan" />
        <span>{(duration / 1000).toFixed(1)}s</span>
      </div>
    </div>
  )
}
