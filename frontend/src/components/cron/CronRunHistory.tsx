import { useQuery } from "@tanstack/react-query"
import { X, CheckCircle2, AlertCircle, Loader2 } from "lucide-react"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface CronRunHistoryProps {
  jobId: string
  open: boolean
  onClose: () => void
}

export function CronRunHistory({ jobId, open, onClose }: CronRunHistoryProps) {
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["cron-runs", jobId],
    queryFn: () => api.listCronRuns(jobId),
    enabled: open,
  })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90] flex items-end sm:items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full sm:max-w-lg sm:mx-4 max-h-[85vh] sm:max-h-[80vh] bg-[hsl(var(--card))] border-t sm:border border-[hsl(var(--border))] rounded-t-lg sm:rounded-sm shadow-xl animate-slide-up flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[hsl(var(--border))]/50">
          <h3 className="text-sm font-mono uppercase tracking-wider font-semibold text-[hsl(var(--foreground))]">
            Execution History
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-[hsl(var(--muted-foreground))]" />
            </div>
          )}

          {!isLoading && runs.length === 0 && (
            <p className="text-center text-sm text-[hsl(var(--muted-foreground))] font-mono py-8">
              No execution history yet
            </p>
          )}

          <div className="space-y-3">
            {runs.map((run: any) => (
              <div
                key={run.id}
                className="rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--surface-1))] p-3"
              >
                <div className="flex items-center gap-2 mb-1.5">
                  {run.status === "ok" ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-[hsl(var(--success))]" />
                  ) : run.status === "running" ? (
                    <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--primary))] animate-spin" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" />
                  )}
                  <span className={cn(
                    "text-xs font-mono uppercase tracking-wider font-medium",
                    run.status === "ok" ? "text-[hsl(var(--success))]"
                      : run.status === "running" ? "text-[hsl(var(--primary))]"
                      : "text-[hsl(var(--destructive))]",
                  )}>
                    {run.status}
                  </span>
                  <span className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono ml-auto tabular-nums">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : ""}
                  </span>
                </div>

                {run.duration_ms > 0 && (
                  <div className="flex items-center gap-3 text-[10px] text-[hsl(var(--muted-foreground))]/70 font-mono mb-1.5">
                    <span>{(run.duration_ms / 1000).toFixed(1)}s</span>
                    {run.total_tokens > 0 && <span>{run.total_tokens} tokens</span>}
                    <span className={cn(
                      "px-1 py-0.5 rounded-sm",
                      run.injected ? "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))]" : "bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]",
                    )}>
                      {run.injected ? "injected" : "pending"}
                    </span>
                  </div>
                )}

                {run.summary_text && (
                  <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono leading-relaxed whitespace-pre-wrap max-h-32 overflow-y-auto">
                    {run.summary_text.slice(0, 300)}{run.summary_text.length > 300 ? "..." : ""}
                  </p>
                )}

                {run.error_message && (
                  <p className="text-xs text-[hsl(var(--destructive))] font-mono mt-1">
                    {run.error_message.slice(0, 200)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
