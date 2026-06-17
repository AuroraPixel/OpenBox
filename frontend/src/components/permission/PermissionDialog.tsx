import { useState } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { usePermissionStore } from "@/stores/permission"
import { api } from "@/services/api"
import type { PermissionRequest } from "@/types"

interface PermissionDialogProps {
  request: PermissionRequest
}

export function PermissionDialog({ request }: PermissionDialogProps) {
  const [loading, setLoading] = useState(false)
  const [showFeedback, setShowFeedback] = useState(false)
  const [feedback, setFeedback] = useState("")
  const removePending = usePermissionStore((s) => s.removePending)

  const handleAction = (action: "once" | "always" | "reject", message?: string) => {
    setLoading(true)
    try {
      api.replyPermission(request.id, action, message || undefined)
      removePending(request.id)
    } catch (e) {
      console.error("Failed to reply permission:", e)
    } finally {
      setLoading(false)
    }
  }

  const handleReject = () => {
    if (showFeedback && feedback.trim()) {
      handleAction("reject", feedback.trim())
    } else if (showFeedback) {
      handleAction("reject")
    } else {
      setShowFeedback(true)
    }
  }

  const isDoomLoop = request.is_doom_loop

  return (
    <Modal open title={isDoomLoop ? "Possible Loop Detected" : "Permission Required"} onClose={() => handleAction("reject")}>
      <div className="p-6 space-y-4 animate-slide-up">
        <div className="flex items-start gap-3">
          {isDoomLoop ? (
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--accent))]/15 flex items-center justify-center shrink-0 glow-amber">
              <RefreshCw className="h-4.5 w-4.5 text-[hsl(var(--accent))]" />
            </div>
          ) : (
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--accent))]/15 flex items-center justify-center shrink-0 glow-amber">
              <AlertTriangle className="h-4.5 w-4.5 text-[hsl(var(--accent))]" />
            </div>
          )}
          <div className="pt-1.5">
            {isDoomLoop ? (
              <p className="text-sm leading-relaxed font-mono">
                Agent has called the same tool repeatedly with identical arguments. This may indicate a loop.
              </p>
            ) : (
              <p className="text-sm leading-relaxed font-mono">Agent wants to execute:</p>
            )}
          </div>
        </div>

        <div className="rounded-sm bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))]/50 p-3.5 font-mono text-sm">
          <span className="text-[hsl(var(--primary))] font-semibold glow-cyan">{request.tool}</span>
          {request.input && (
            <span className="text-[hsl(var(--muted-foreground))]">
              : {JSON.stringify(request.input).slice(0, 200)}
            </span>
          )}
        </div>

        {showFeedback && (
          <div className="space-y-1.5 animate-fade-in">
            <label className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Feedback (optional)</label>
            <input
              type="text"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleReject() }}
              placeholder="Tell the agent what to do instead..."
              className="w-full px-3.5 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/30 transition-all"
              autoFocus
            />
          </div>
        )}

        <div className="flex justify-end gap-2.5 pt-2">
          <button
            onClick={isDoomLoop ? () => handleAction("reject") : handleReject}
            disabled={loading}
            className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--border))] transition-all cursor-pointer disabled:opacity-50"
          >
            {isDoomLoop ? "Stop Agent" : showFeedback ? "Confirm Reject" : "Reject"}
          </button>
          <button
            onClick={() => handleAction("once")}
            disabled={loading}
            className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--permission-allow))]/30 text-[hsl(var(--permission-allow))] hover:bg-[hsl(var(--permission-allow))]/10 transition-all cursor-pointer disabled:opacity-50"
          >
            Allow Once
          </button>
          {!isDoomLoop && (
            <button
              onClick={() => handleAction("always")}
              disabled={loading}
              className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--permission-allow))] text-white hover:opacity-90 transition-opacity cursor-pointer disabled:opacity-50 glow-green"
            >
              Allow Always
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}
