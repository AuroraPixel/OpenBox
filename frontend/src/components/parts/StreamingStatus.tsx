import { useState, useEffect, useRef, useMemo } from "react"
import { Zap, Brain, PenLine, Loader2 } from "lucide-react"
import type { MessageWithParts } from "@/types"

interface StreamingStatusProps {
  message: MessageWithParts
}

type Phase = "inferring" | "thinking" | "writing" | "running"

function formatDuration(ms: number): string {
  const totalSecs = Math.floor(ms / 1000)
  if (totalSecs < 60) return `${totalSecs}s`
  const mins = Math.floor(totalSecs / 60)
  const secs = totalSecs % 60
  return `${mins}m ${secs.toString().padStart(2, "0")}s`
}

function formatTokens(chars: number): string {
  const tokens = Math.round(chars / 4)
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(tokens)
}

export function StreamingStatus({ message }: StreamingStatusProps) {
  const [now, setNow] = useState(Date.now())
  const reasoningStartRef = useRef<number | null>(null)
  const textStartRef = useRef<number | null>(null)

  // Tick every second
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  // Detect phase and collect stats from parts
  const { phase, runningTool, totalChars, hasReasoning, hasText } = useMemo(() => {
    let phase: Phase = "inferring"
    let runningTool = ""
    let totalChars = 0
    let hasReasoning = false
    let hasText = false

    for (const p of message.parts) {
      if (p.type === "reasoning") {
        hasReasoning = true
        totalChars += p.text.length
      }
      if (p.type === "text" && !(p as { synthetic?: boolean }).synthetic) {
        hasText = true
        totalChars += p.text.length
      }
      if (p.type === "tool" && (p.status === "running" || p.status === "pending")) {
        runningTool = p.tool
      }
    }

    if (runningTool) {
      phase = "running"
    } else if (hasReasoning && !hasText) {
      phase = "thinking"
    } else if (hasText) {
      phase = "writing"
    }

    return { phase, runningTool, totalChars, hasReasoning, hasText }
  }, [message.parts])

  // Track reasoning/text start times
  useEffect(() => {
    if (hasReasoning && !reasoningStartRef.current) {
      reasoningStartRef.current = Date.now()
    }
  }, [hasReasoning])

  useEffect(() => {
    if (hasText && !textStartRef.current) {
      textStartRef.current = Date.now()
    }
  }, [hasText])

  // Reset refs when message changes
  useEffect(() => {
    reasoningStartRef.current = null
    textStartRef.current = null
  }, [message.id])

  // Compute durations
  const elapsed = now - new Date(message.created_at).getTime()

  let thinkingDuration: number | null = null
  if (reasoningStartRef.current) {
    if (textStartRef.current) {
      thinkingDuration = textStartRef.current - reasoningStartRef.current
    } else {
      thinkingDuration = now - reasoningStartRef.current
    }
  }

  // Phase icon & label
  const phaseDisplay = {
    inferring: { icon: <Zap className="h-3 w-3 text-[hsl(var(--accent))] glow-amber" />, label: "Inferring" },
    thinking: { icon: <Brain className="h-3 w-3 text-violet-400" />, label: "Thinking" },
    writing: { icon: <PenLine className="h-3 w-3 text-[hsl(var(--primary))] glow-cyan" />, label: "Writing" },
    running: { icon: <Loader2 className="h-3 w-3 text-[hsl(var(--primary))] animate-spin glow-cyan" />, label: `Running ${runningTool}` },
  }

  const { icon, label } = phaseDisplay[phase]

  return (
    <div className="flex items-center gap-3 py-1.5 text-[10px] text-[hsl(var(--muted-foreground))]/70 tabular-nums font-mono">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="font-mono uppercase tracking-wider font-medium">{label}</span>
        {(phase === "inferring" || phase === "thinking") && (
          <span className="flex items-center gap-0.5 ml-0.5">
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" />
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" style={{ animationDelay: "0.2s" }} />
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" style={{ animationDelay: "0.4s" }} />
          </span>
        )}
      </div>
      <span>{formatDuration(elapsed)}</span>
      {totalChars > 0 && (
        <span>~{formatTokens(totalChars)} tokens</span>
      )}
      {thinkingDuration !== null && thinkingDuration > 1000 && (
        <span>thought {formatDuration(thinkingDuration)}</span>
      )}
    </div>
  )
}
