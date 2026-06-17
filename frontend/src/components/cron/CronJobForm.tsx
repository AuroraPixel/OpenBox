import { useState } from "react"
import { Loader2 } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { useToast } from "@/components/ui/Toast"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface CronJobFormProps {
  open: boolean
  sessionId: string
  onClose: () => void
  onCreated: () => void
}

export function CronJobForm({ open, sessionId, onClose, onCreated }: CronJobFormProps) {
  const { addToast } = useToast()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const [name, setName] = useState("")
  const [scheduleType, setScheduleType] = useState<"cron" | "every">("cron")
  const [cronExpr, setCronExpr] = useState("0 9 * * *")
  const [timezone, setTimezone] = useState("UTC")
  const [everyValue, setEveryValue] = useState("30")
  const [everyUnit, setEveryUnit] = useState<"m" | "h">("m")
  const [taskPrompt, setTaskPrompt] = useState("")

  const handleSubmit = async () => {
    if (!name.trim() || !taskPrompt.trim()) {
      setError("Name and task are required")
      return
    }

    setLoading(true)
    setError("")

    try {
      const schedule = scheduleType === "cron"
        ? { kind: "cron", expr: cronExpr, tz: timezone }
        : { kind: "every", every_ms: parseInt(everyValue) * (everyUnit === "h" ? 3600000 : 60000) }

      await api.createCronJob({
        session_id: sessionId,
        name: name.trim(),
        schedule,
        task_prompt: taskPrompt.trim(),
      })

      addToast("success", `"${name}" created`)
      onCreated()
      _reset()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create")
    } finally {
      setLoading(false)
    }
  }

  const _reset = () => {
    setName("")
    setCronExpr("0 9 * * *")
    setEveryValue("30")
    setTaskPrompt("")
    setError("")
  }

  return (
    <Modal open={open} onClose={onClose} title="New Scheduled Task">
      <div className="p-6 space-y-5 animate-slide-up">
        {/* Name */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Daily Report"
            className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
          />
        </div>

        {/* Schedule Type */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">Schedule</label>
          <div className="flex gap-2 mb-2">
            <button
              onClick={() => setScheduleType("cron")}
              className={cn(
                "px-3 py-1.5 text-xs font-mono rounded-sm border transition-all cursor-pointer",
                scheduleType === "cron"
                  ? "border-[hsl(var(--primary))]/50 bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]"
                  : "border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:border-[hsl(var(--primary))]/30",
              )}
            >
              Cron Expression
            </button>
            <button
              onClick={() => setScheduleType("every")}
              className={cn(
                "px-3 py-1.5 text-xs font-mono rounded-sm border transition-all cursor-pointer",
                scheduleType === "every"
                  ? "border-[hsl(var(--primary))]/50 bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]"
                  : "border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:border-[hsl(var(--primary))]/30",
              )}
            >
              Interval
            </button>
          </div>

          {scheduleType === "cron" ? (
            <div className="space-y-2">
              <input
                type="text"
                value={cronExpr}
                onChange={(e) => setCronExpr(e.target.value)}
                placeholder="0 9 * * *"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all"
              />
              <div className="flex items-center gap-2">
                <label className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]">Timezone:</label>
                <input
                  type="text"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  placeholder="UTC"
                  className="w-40 px-2 py-1.5 text-xs font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all"
                />
              </div>
              <p className="text-[10px] text-[hsl(var(--muted-foreground))]/60 font-mono">
                Examples: <code className="text-[hsl(var(--primary))]">0 9 * * *</code> (daily 9am) · <code className="text-[hsl(var(--primary))]">*/30 * * * *</code> (every 30min)
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-[hsl(var(--muted-foreground))]">Every</span>
              <input
                type="number"
                value={everyValue}
                onChange={(e) => setEveryValue(e.target.value)}
                min="1"
                className="w-20 px-2 py-2 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all"
              />
              <select
                value={everyUnit}
                onChange={(e) => setEveryUnit(e.target.value as "m" | "h")}
                className="px-2 py-2 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all cursor-pointer"
              >
                <option value="m">minutes</option>
                <option value="h">hours</option>
              </select>
            </div>
          )}
        </div>

        {/* Task Prompt */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">Task Prompt</label>
          <textarea
            value={taskPrompt}
            onChange={(e) => setTaskPrompt(e.target.value)}
            rows={4}
            placeholder="What should the agent do on each run?"
            className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 transition-all font-mono resize-y"
          />
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] font-mono">
            <div className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--destructive))] shrink-0" />
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className={cn(
              "px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
              "hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed",
              "flex items-center gap-2 glow-cyan",
            )}
          >
            {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create
          </button>
        </div>
      </div>
    </Modal>
  )
}
