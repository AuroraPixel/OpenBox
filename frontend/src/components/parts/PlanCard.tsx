import { useState, useEffect, useCallback } from "react"
import { ChevronRight, ChevronDown, Check, X, Loader2, FileText, Maximize2, Pencil } from "lucide-react"
import { cn } from "@/lib/utils"
import type { PlanPartData, PlanStatus } from "@/types"
import { useSessionStore } from "@/stores/session"
import { api } from "@/services/api"
import { PlanModal } from "./PlanModal"

interface PlanCardProps {
  part: PlanPartData
  sessionId: string
}

const statusConfig: Record<PlanStatus, {
  icon: React.ReactNode
  label: string
  borderClass: string
  bgClass: string
}> = {
  writing: {
    icon: <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--tool-running))] animate-spin" />,
    label: "Writing plan...",
    borderClass: "border-[hsl(var(--primary))]/20",
    bgClass: "bg-[hsl(var(--primary))]/5",
  },
  ready: {
    icon: <FileText className="h-3.5 w-3.5 text-[hsl(var(--primary))] glow-cyan" />,
    label: "Plan ready — review and accept",
    borderClass: "border-[hsl(var(--primary))]/30",
    bgClass: "bg-[hsl(var(--primary))]/5",
  },
  accepted: {
    icon: <Check className="h-3.5 w-3.5 text-[hsl(var(--tool-completed))] glow-green" />,
    label: "Plan accepted",
    borderClass: "border-[hsl(var(--tool-completed))]/20",
    bgClass: "bg-[hsl(var(--tool-completed))]/5",
  },
  rejected: {
    icon: <X className="h-3.5 w-3.5 text-[hsl(var(--tool-error))] glow-coral" />,
    label: "Plan rejected",
    borderClass: "border-[hsl(var(--tool-error))]/20",
    bgClass: "bg-[hsl(var(--tool-error))]/5",
  },
}

export function PlanCard({ part, sessionId }: PlanCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [liveContent, setLiveContent] = useState(part.content)
  const [acting, setActing] = useState(false)
  const planVersion = useSessionStore((s) => s.planVersion)

  // Live-refresh content while plan is being written
  useEffect(() => {
    if (part.status !== "writing") {
      setLiveContent(part.content)
      return
    }
    let cancelled = false
    api.getPlan(sessionId).then((data) => {
      if (!cancelled && data?.content) {
        setLiveContent(data.content)
      }
    }).catch(() => {})
    return () => { cancelled = true }
  }, [part.status, part.content, sessionId, planVersion])

  // Auto-expand when content first arrives
  useEffect(() => {
    if (liveContent && !expanded) {
      setExpanded(true)
    }
  }, [liveContent])

  const handleRefresh = useCallback(async () => {
    try {
      const data = await api.getPlan(sessionId)
      if (data?.content) setLiveContent(data.content)
    } catch {}
  }, [sessionId])

  const handleAccept = useCallback(async () => {
    setActing(true)
    try {
      await api.acceptPlan(sessionId)
    } catch {} finally {
      setActing(false)
    }
  }, [sessionId])

  const handleReject = useCallback(async () => {
    setActing(true)
    try {
      await api.rejectPlan(sessionId)
    } catch {} finally {
      setActing(false)
    }
  }, [sessionId])

  const config = statusConfig[part.status]
  const previewLines = liveContent
    ? liveContent.split("\n").slice(0, 6).join("\n")
    : ""

  return (
    <>
      <div className={cn(
        "rounded-sm border overflow-hidden shadow-[0_0_8px_hsl(var(--primary)/0.1)]",
        config.borderClass,
        config.bgClass,
      )}>
        {/* Header */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs hover:bg-[hsl(var(--surface-1))] transition-colors cursor-pointer"
        >
          {expanded
            ? <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
            : <ChevronRight className="h-3 w-3 shrink-0 opacity-60" />
          }
          {config.icon}
          <span className="font-display font-medium text-[hsl(var(--primary))]">Plan</span>
          <span className="text-[hsl(var(--muted-foreground))] truncate flex-1 text-left font-mono">
            {config.label}
          </span>
          {(part.status === "writing" || part.status === "ready") && (
            <span
              role="button"
              tabIndex={0}
              className="p-1 rounded-sm hover:bg-[hsl(var(--muted))]/60 transition-colors shrink-0 cursor-pointer"
              onClick={(e) => { e.stopPropagation(); setModalOpen(true) }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setModalOpen(true) } }}
              title="Edit plan"
            >
              <Pencil className="h-3 w-3 text-[hsl(var(--muted-foreground))]" />
            </span>
          )}
          <span
            role="button"
            tabIndex={0}
            className="p-1 rounded-sm hover:bg-[hsl(var(--muted))]/60 transition-colors shrink-0 cursor-pointer"
            onClick={(e) => { e.stopPropagation(); setModalOpen(true) }}
            onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setModalOpen(true) } }}
            title="View full plan"
          >
            <Maximize2 className="h-3 w-3 text-[hsl(var(--muted-foreground))]" />
          </span>
        </button>

        {/* Expanded preview */}
        {expanded && liveContent && (
          <div className="border-t border-[hsl(var(--border))]/30 text-xs animate-fade-in">
            <div className="p-3.5 bg-[hsl(var(--terminal-bg))]">
              <pre className="text-[11px] font-mono whitespace-pre-wrap overflow-x-auto text-[hsl(var(--foreground))]/80 max-h-32 overflow-y-auto leading-relaxed">
                {previewLines}
              </pre>
              {liveContent.split("\n").length > 6 && (
                <button
                  onClick={() => setModalOpen(true)}
                  className="mt-2.5 text-[hsl(var(--primary))] hover:text-[hsl(var(--primary))]/80 text-[11px] cursor-pointer transition-colors font-mono uppercase tracking-wider"
                >
                  View full plan...
                </button>
              )}
            </div>

            {/* Accept / Reject buttons */}
            {part.status === "ready" && (
              <div className="flex items-center gap-2.5 px-3.5 py-2.5 border-t border-[hsl(var(--border))]/30">
                <button
                  onClick={handleAccept}
                  disabled={acting}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 disabled:opacity-50 cursor-pointer shadow-[0_0_8px_hsl(var(--primary)/0.3)] transition-opacity"
                >
                  {acting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                  Accept Plan
                </button>
                <button
                  onClick={handleReject}
                  disabled={acting}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 disabled:opacity-50 cursor-pointer transition-colors"
                >
                  <X className="h-3 w-3" />
                  Reject
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal */}
      <PlanModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        content={liveContent}
        path={part.path}
        status={part.status}
        sessionId={sessionId}
        onRefresh={handleRefresh}
        onAccept={handleAccept}
        onReject={handleReject}
      />
    </>
  )
}
