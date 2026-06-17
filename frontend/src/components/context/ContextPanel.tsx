import { Zap, Layers, Activity } from "lucide-react"
import { useSessionStore } from "@/stores/session"
import { Progress } from "@/components/ui/Progress"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

export function ContextPanel() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === currentSessionId))
  const tokenUsage = session?.token_usage

  if (!tokenUsage) return null

  // Context window = last step's input tokens (what the LLM actually received).
  // This is what matters for overflow detection, NOT cumulative total.
  const contextUsed = tokenUsage.context || 0
  const contextLimit = tokenUsage.limit || 200_000
  const contextPercent = contextLimit > 0 ? (contextUsed / contextLimit) * 100 : 0
  const isNearLimit = contextPercent > 80
  const isOverLimit = contextPercent > 95

  // Cumulative totals across all LLM calls in this session
  const totalInput = tokenUsage.input || 0
  const totalOutput = tokenUsage.output || 0
  const totalCost = tokenUsage.cost ?? 0

  const handleCompact = async () => {
    if (!currentSessionId) return
    try {
      await api.summarize(currentSessionId)
    } catch (e) {
      console.error("Failed to compact:", e)
    }
  }

  return (
    <div className="px-4 py-3">
      <h3 className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-3 flex items-center gap-2">
        <div className="h-5 w-5 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
          <Zap className="h-3 w-3 text-[hsl(var(--primary))]" />
        </div>
        Context
      </h3>
      <div className="space-y-3">
        {/* Context Window — the real metric that matters */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <div className="flex items-center gap-1.5 text-[hsl(var(--muted-foreground))] font-mono">
              <Activity className="h-3 w-3" />
              Context Window
            </div>
            <span className={cn(
              "text-[10px] tabular-nums font-mono font-medium",
              isOverLimit ? "text-[hsl(var(--destructive))]" : isNearLimit ? "text-[hsl(var(--accent))]" : "text-[hsl(var(--primary))]",
            )}>
              {(contextUsed / 1000).toFixed(0)}K / {(contextLimit / 1000).toFixed(0)}K
            </span>
          </div>
          <Progress
            value={contextUsed}
            max={contextLimit}
            className={cn(isOverLimit && "!bg-[hsl(var(--destructive))]/20", isNearLimit && !isOverLimit && "!bg-[hsl(var(--accent))]/20")}
          />
        </div>

        {/* Session cumulative stats */}
        <div className="grid grid-cols-3 gap-2.5 text-center">
          <div className="rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/50 px-2 py-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Total In</div>
            <div className="text-xs font-mono font-semibold tabular-nums mt-0.5 text-[hsl(var(--primary))]">{(totalInput / 1000).toFixed(1)}K</div>
          </div>
          <div className="rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/50 px-2 py-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Total Out</div>
            <div className="text-xs font-mono font-semibold tabular-nums mt-0.5 text-[hsl(var(--accent))]">{(totalOutput / 1000).toFixed(1)}K</div>
          </div>
          <div className="rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/50 px-2 py-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Cost</div>
            <div className="text-xs font-mono font-semibold tabular-nums mt-0.5 text-[hsl(var(--success))]">${totalCost.toFixed(4)}</div>
          </div>
        </div>

        <div className="flex items-center justify-end">
          <button
            onClick={handleCompact}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider rounded-sm border transition-all cursor-pointer",
              isNearLimit
                ? "border-[hsl(var(--accent))]/50 bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/20"
                : "border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--primary))]/30",
            )}
          >
            <Layers className="h-3 w-3" />
            Compact
          </button>
        </div>
      </div>
    </div>
  )
}
