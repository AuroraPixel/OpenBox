import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Clock, Plus, Trash2, Play, Pause, PlayCircle, Loader2, History } from "lucide-react"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useToast } from "@/components/ui/Toast"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"
import { CronJobForm } from "./CronJobForm"
import { CronRunHistory } from "./CronRunHistory"

interface CronJobListProps {
  sessionId?: string  // If provided, filter by session
  showSessionInfo?: boolean  // Show session name in global view
  compact?: boolean  // Compact mode for sidebar
}

const statusConfig: Record<string, { color: string; bgColor: string; dotColor: string }> = {
  ok: { color: "text-[hsl(var(--success))]", bgColor: "bg-[hsl(var(--success))]/10", dotColor: "bg-[hsl(var(--success))]" },
  error: { color: "text-[hsl(var(--destructive))]", bgColor: "bg-[hsl(var(--destructive))]/10", dotColor: "bg-[hsl(var(--destructive))]" },
  running: { color: "text-[hsl(var(--primary))]", bgColor: "bg-[hsl(var(--primary))]/10", dotColor: "bg-[hsl(var(--primary))]" },
  skipped: { color: "text-[hsl(var(--accent))]", bgColor: "bg-[hsl(var(--accent))]/10", dotColor: "bg-[hsl(var(--accent))]" },
  pending: { color: "text-[hsl(var(--muted-foreground))]", bgColor: "bg-[hsl(var(--muted))]", dotColor: "bg-[hsl(var(--muted-foreground))]" },
}

export function CronJobList({ sessionId, showSessionInfo: _showSessionInfo, compact }: CronJobListProps) {
  void _showSessionInfo
  const queryClient = useQueryClient()
  const { addToast } = useToast()
  const [formOpen, setFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)
  const [historyTarget, setHistoryTarget] = useState<string | null>(null)

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["cron-jobs", sessionId],
    queryFn: () => api.listCronJobs(sessionId),
    refetchInterval: 10000,
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["cron-jobs"] })

  const handleToggle = async (jobId: string, enabled: boolean) => {
    try {
      await api.updateCronJob(jobId, { enabled })
      addToast("success", enabled ? "Job enabled" : "Job paused")
      refresh()
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : "Failed to update job")
    }
  }

  const handleRun = async (jobId: string) => {
    try {
      await api.runCronJob(jobId)
      addToast("info", "Job triggered")
      refresh()
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : "Failed to run job")
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await api.deleteCronJob(deleteTarget.id)
      addToast("success", `"${deleteTarget.name}" deleted`)
      setDeleteTarget(null)
      refresh()
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : "Failed to delete job")
    }
  }

  if (isLoading) {
    return <div className="flex items-center justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-[hsl(var(--muted-foreground))]" /></div>
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className={cn(
            "font-display uppercase tracking-wider text-[hsl(var(--foreground))]",
            compact ? "text-sm" : "text-lg",
          )}>
            {compact ? "Scheduled Tasks" : "Cron Jobs"}
          </h2>
          <p className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mt-0.5">
            {jobs.length} task{jobs.length !== 1 ? "s" : ""}
          </p>
        </div>
        {sessionId && (
          <button
            onClick={() => setFormOpen(true)}
            className={cn(
              "flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              compact
                ? "px-2.5 py-1.5 border border-[hsl(var(--primary))]/30 text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10"
                : "px-4 py-2 bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 glow-cyan",
            )}
          >
            <Plus className="h-3 w-3" />
            {compact ? "Add" : "New Task"}
          </button>
        )}
      </div>

      {/* Job Cards */}
      <div className={cn(
        "grid overflow-y-auto",
        compact ? "gap-2 max-h-[50vh]" : "gap-3 max-h-[calc(100vh-280px)]",
      )}>
        {jobs.map((job: any) => {
          const st = statusConfig[job.running ? "running" : (job.last_status || "pending")] || statusConfig.pending
          const scheduleText = _formatSchedule(job.schedule)

          return (
            <div
              key={job.id}
              className={cn(
                "rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] transition-colors group",
                compact ? "p-3" : "p-3 sm:p-4",
                "hover:border-[hsl(var(--primary))]/40",
              )}
            >
              <div className={cn("flex gap-2 sm:gap-3", compact ? "items-center" : "items-start")}>
                {/* Icon — hidden on mobile for non-compact */}
                {!compact && (
                  <div className="hidden sm:flex h-10 w-10 rounded-sm bg-[hsl(var(--primary))]/10 items-center justify-center shrink-0 glow-cyan">
                    <Clock className="h-5 w-5 text-[hsl(var(--primary))]" />
                  </div>
                )}

                {/* Content */}
                <div className="flex-1 min-w-0 overflow-hidden">
                  <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                    <span className={cn("font-display uppercase tracking-wider truncate max-w-[150px] sm:max-w-[200px]", compact ? "text-xs" : "text-sm")} title={job.name}>
                      {job.name}
                    </span>
                    {/* Status badge */}
                    <span className={cn(
                      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-mono uppercase tracking-wider shrink-0",
                      st.bgColor, st.color,
                    )}>
                      <span className={cn("h-1.5 w-1.5 rounded-full", st.dotColor, job.running && "animate-pulse")} />
                      {job.running ? "running" : (job.last_status || "pending")}
                    </span>
                    {!job.enabled && (
                      <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-mono uppercase tracking-wider bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] shrink-0">
                        paused
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-[hsl(var(--muted-foreground))] font-mono truncate">
                    {scheduleText}
                    {job.next_run_at && job.enabled && (
                      <> · Next: {_formatRelativeTime(job.next_run_at)}</>
                    )}
                  </p>

                  {/* Where it runs. A scheduled task acts on files, and the
                      directory is the part you cannot infer from the prompt. */}
                  {job.project_directory && (
                    <p className="text-[10px] text-[hsl(var(--muted-foreground))]/60 font-mono truncate mt-0.5">
                      {job.project_directory}
                    </p>
                  )}

                  {!compact && (
                    <p className="text-xs text-[hsl(var(--muted-foreground))]/70 mt-1 line-clamp-2 break-all">
                      {job.task_prompt}
                    </p>
                  )}

                  {!compact && job.last_run_at && (
                    <p className="text-[10px] text-[hsl(var(--muted-foreground))]/60 font-mono mt-1 truncate">
                      Last: {_formatRelativeTime(job.last_run_at)}
                      {job.last_duration_ms && <> · {(job.last_duration_ms / 1000).toFixed(1)}s</>}
                      {job.total_runs > 0 && <> · {job.total_successes}/{job.total_runs} runs</>}
                    </p>
                  )}
                </div>

                {/* Actions */}
                <div className={cn(
                  "flex items-center shrink-0",
                  compact ? "gap-0.5" : "gap-1 sm:gap-1.5 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity",
                )}>
                  <button
                    onClick={() => handleRun(job.id)}
                    disabled={job.running}
                    className="p-1.5 rounded-sm text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10 transition-all cursor-pointer disabled:opacity-30"
                    title="Run now"
                  >
                    <PlayCircle className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleToggle(job.id, !job.enabled)}
                    className={cn(
                      "p-1.5 rounded-sm transition-all cursor-pointer",
                      job.enabled
                        ? "text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/10"
                        : "text-[hsl(var(--success))] hover:bg-[hsl(var(--success))]/10",
                    )}
                    title={job.enabled ? "Pause" : "Resume"}
                  >
                    {job.enabled ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  </button>
                  {!compact && (
                    <button
                      onClick={() => setHistoryTarget(job.id)}
                      className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer"
                      title="Run history"
                    >
                      <History className="h-3.5 w-3.5" />
                    </button>
                  )}
                  <button
                    onClick={() => setDeleteTarget({ id: job.id, name: job.name })}
                    className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 transition-all cursor-pointer"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )
        })}

        {/* Empty state */}
        {jobs.length === 0 && (
          <div className={cn(
            "rounded-sm border border-dashed border-[hsl(var(--border))] text-center",
            compact ? "p-6" : "p-10 grid-pattern",
          )}>
            <Clock className={cn("mx-auto mb-2 text-[hsl(var(--muted-foreground))]/40", compact ? "h-6 w-6" : "h-8 w-8")} />
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No scheduled tasks</p>
            {sessionId && (
              <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1">
                Click "Add" to create a scheduled task
              </p>
            )}
          </div>
        )}
      </div>

      {/* Dialogs */}
      {sessionId && (
        <CronJobForm
          open={formOpen}
          sessionId={sessionId}
          onClose={() => setFormOpen(false)}
          onCreated={refresh}
        />
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Scheduled Task"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {historyTarget && (
        <CronRunHistory
          jobId={historyTarget}
          open={!!historyTarget}
          onClose={() => setHistoryTarget(null)}
        />
      )}
    </div>
  )
}

// Helpers
function _formatSchedule(schedule: any): string {
  if (!schedule) return "Unknown"
  if (schedule.kind === "cron") return `${schedule.expr}${schedule.tz !== "UTC" ? ` (${schedule.tz})` : ""}`
  if (schedule.kind === "every") {
    const ms = schedule.every_ms
    if (ms >= 3600000) return `Every ${ms / 3600000}h`
    if (ms >= 60000) return `Every ${ms / 60000}m`
    return `Every ${ms / 1000}s`
  }
  if (schedule.kind === "at") return `Once: ${schedule.at}`
  return JSON.stringify(schedule)
}

function _formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 0) {
    const abs = -diff
    if (abs < 60000) return "in <1m"
    if (abs < 3600000) return `in ${Math.round(abs / 60000)}m`
    if (abs < 86400000) return `in ${Math.round(abs / 3600000)}h`
    return `in ${Math.round(abs / 86400000)}d`
  }
  if (diff < 60000) return "<1m ago"
  if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.round(diff / 3600000)}h ago`
  return `${Math.round(diff / 86400000)}d ago`
}
