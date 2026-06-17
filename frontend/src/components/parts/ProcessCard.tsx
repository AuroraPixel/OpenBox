import { useState, useEffect, useRef, useMemo } from "react"
import { ChevronRight, ChevronDown, Check, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { MessagePart, ToolPartData, StepFinishPart } from "@/types"

interface ProcessCardProps {
  parts: MessagePart[]
  renderPart: (part: MessagePart) => React.ReactNode
  isStreaming?: boolean
}

function getToolLabel(part: ToolPartData): string {
  const input = part.input || {}
  switch (part.tool) {
    case "bash": {
      const cmd = String(input.command || "").slice(0, 50)
      return cmd ? `bash: ${cmd}` : "bash"
    }
    case "read":
    case "write":
    case "edit":
      return `${part.tool}: ${String(input.file_path || input.path || "").split("/").pop() || ""}`
    case "glob":
      return `glob: ${String(input.pattern || "")}`
    case "grep":
      return `grep: ${String(input.pattern || "")}`
    case "web_search":
      return `web_search: ${String(input.query || "")}`
    case "task":
      return `task: ${String(input.description || "").slice(0, 40)}`
    default:
      return part.title || part.tool
  }
}

export function ProcessCard({ parts, renderPart, isStreaming }: ProcessCardProps) {
  const [userToggled, setUserToggled] = useState(false)
  const [userExpanded, setUserExpanded] = useState(false)
  const prevActiveRef = useRef(false)

  const { isActive, statusText, totalDuration: _totalDuration, hasError } = useMemo(() => {
    let isActive = false
    let lastActiveLabel = ""
    let stepCount = 0
    let totalDuration = 0
    let totalCost = 0
    let hasError = false
    let lastCompletedLabel = ""

    for (const p of parts) {
      if (p.type === "tool") {
        const tool = p as ToolPartData
        if (tool.status === "running" || tool.status === "pending") {
          isActive = true
          lastActiveLabel = getToolLabel(tool)
        }
        if (tool.status === "completed") {
          lastCompletedLabel = getToolLabel(tool)
        }
        if (tool.status === "error") hasError = true
      }
      if (p.type === "step-finish") {
        const sf = p as StepFinishPart
        stepCount++
        totalDuration += sf.duration
        totalCost += sf.cost
      }
    }

    if (isStreaming && !isActive) {
      isActive = true
    }

    let statusText: string
    if (isActive) {
      statusText = lastActiveLabel || lastCompletedLabel || "Thinking..."
    } else {
      const stepLabel = stepCount <= 1 ? "1 step" : `${stepCount} steps`
      const dur = totalDuration > 0 ? ` · ${(totalDuration / 1000).toFixed(1)}s` : ""
      const cost = totalCost > 0 ? ` · $${totalCost.toFixed(4)}` : ""
      // Show the last action as context
      const lastAction = lastCompletedLabel ? ` — ${lastCompletedLabel}` : ""
      statusText = `${stepLabel}${dur}${cost}${lastAction}`
    }

    return { isActive, statusText, totalDuration, hasError }
  }, [parts, isStreaming])

  // Determine if expanded: user override takes priority, otherwise expand when active
  const expanded = userToggled ? userExpanded : isActive

  const handleToggle = () => {
    setUserToggled(true)
    setUserExpanded(!expanded)
  }

  // Reset user toggle when activity starts (so auto-expand works)
  useEffect(() => {
    if (isActive && !prevActiveRef.current) {
      setUserToggled(false)
    }
    prevActiveRef.current = isActive
  }, [isActive])

  return (
    <div className={cn(
      "rounded-sm border overflow-hidden shadow-[0_0_6px_hsl(var(--primary)/0.08)]",
      hasError
        ? "border-[hsl(var(--tool-error))]/20 bg-[hsl(var(--card))]"
        : "border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]",
    )}>
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs hover:bg-[hsl(var(--surface-1))] transition-colors cursor-pointer"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 shrink-0 opacity-60" />
          : <ChevronRight className="h-3 w-3 shrink-0 opacity-60" />
        }
        {isActive ? (
          <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--tool-running))] animate-spin glow-cyan shrink-0" />
        ) : hasError ? (
          <Check className="h-3.5 w-3.5 text-[hsl(var(--accent))] shrink-0" />
        ) : (
          <Check className="h-3.5 w-3.5 text-[hsl(var(--tool-completed))] glow-green shrink-0" />
        )}
        <span className="text-[hsl(var(--muted-foreground))] truncate flex-1 text-left font-mono">
          {statusText}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-[hsl(var(--border))]/30 px-3 py-2.5 space-y-2.5 animate-fade-in">
          {parts.map((part) => (
            <div key={part.id}>{renderPart(part)}</div>
          ))}
        </div>
      )}
    </div>
  )
}
