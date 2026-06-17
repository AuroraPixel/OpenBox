import { useState, useEffect, useRef, memo } from "react"
import { ChevronRight, ChevronDown, Check, X, Loader2, Timer } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ToolPartData } from "@/types"
import { ToolBash } from "./ToolBash"
import { ToolRead } from "./ToolRead"
import { ToolEdit } from "./ToolEdit"
import { ToolGrep } from "./ToolGrep"
import { ToolGlob } from "./ToolGlob"
import { ToolTask } from "./ToolTask"

interface ToolPartProps {
  part: ToolPartData
}

const statusIcons: Record<string, React.ReactNode> = {
  pending: <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--tool-pending))] animate-spin" />,
  running: <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--tool-running))] animate-spin glow-cyan" />,
  completed: <Check className="h-3.5 w-3.5 text-[hsl(var(--tool-completed))] glow-green" />,
  error: <X className="h-3.5 w-3.5 text-[hsl(var(--tool-error))] glow-coral" />,
}

export const ToolPart = memo(function ToolPart({ part }: ToolPartProps) {
  // _streamingArgs is raw JSON being accumulated during LLM streaming
  const streamingArgs = (part as any)._streamingArgs as string | undefined
  const isStreaming = part.status === "pending" && !!streamingArgs

  const [expanded, setExpanded] = useState(false)

  // Auto-expand for streaming tool calls (so user sees content being generated)
  useEffect(() => {
    if (isStreaming && !expanded) {
      setExpanded(true)
    }
  }, [isStreaming])

  // Auto-expand when running tool gets output (real-time streaming)
  useEffect(() => {
    if (part.status === "running" && part.output && !expanded) {
      setExpanded(true)
    }
  }, [part.status, part.output])

  // Timer + idle detection for running bash commands
  const startTimeRef = useRef<number | null>(null)
  const lastOutputRef = useRef<string | undefined>(undefined)
  const lastOutputTimeRef = useRef<number>(Date.now())
  const [elapsed, setElapsed] = useState(0)
  const [idleSecs, setIdleSecs] = useState(0)

  const isBashRunning = part.tool === "bash" && part.status === "running"

  // Track when output last changed
  useEffect(() => {
    if (isBashRunning && part.output !== lastOutputRef.current) {
      lastOutputRef.current = part.output
      lastOutputTimeRef.current = Date.now()
    }
  }, [isBashRunning, part.output])

  useEffect(() => {
    if (isBashRunning) {
      if (!startTimeRef.current) {
        startTimeRef.current = Date.now()
        lastOutputTimeRef.current = Date.now()
      }
      const timer = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current!) / 1000))
        setIdleSecs(Math.floor((Date.now() - lastOutputTimeRef.current) / 1000))
      }, 1000)
      return () => clearInterval(timer)
    } else {
      startTimeRef.current = null
      setElapsed(0)
      setIdleSecs(0)
    }
  }, [isBashRunning])

  const isIdle = isBashRunning && idleSecs >= 5

  const title = part.title || (isStreaming ? getStreamingTitle(part, streamingArgs) : getToolTitle(part))
  const duration = part.duration ? `${(part.duration / 1000).toFixed(1)}s` : null

  return (
    <div className={cn(
      "rounded-sm border overflow-hidden shadow-[0_0_6px_hsl(var(--primary)/0.08)]",
      part.status === "error"
        ? "border-[hsl(var(--tool-error))]/20 bg-[hsl(var(--tool-error))]/5"
        : "border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]",
    )}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs hover:bg-[hsl(var(--surface-1))] transition-colors cursor-pointer"
      >
        {expanded ? <ChevronDown className="h-3 w-3 shrink-0 opacity-60" /> : <ChevronRight className="h-3 w-3 shrink-0 opacity-60" />}
        {statusIcons[part.status]}
        <span className="font-mono font-medium text-[hsl(var(--primary))]">{part.tool}</span>
        <span className="text-[hsl(var(--muted-foreground))] truncate flex-1 text-left font-mono">{title}</span>
        {isBashRunning ? (
          <span className={cn(
            "flex items-center gap-1.5 text-[10px] font-mono shrink-0 tabular-nums",
            isIdle ? "text-[hsl(var(--accent))] glow-amber" : "text-[hsl(var(--muted-foreground))]/70",
          )}>
            <Timer className="h-3 w-3" />
            {isIdle ? `idle ${idleSecs}s` : `${elapsed}s`}
          </span>
        ) : duration ? (
          <span className="text-[hsl(var(--muted-foreground))]/60 text-[10px] shrink-0 tabular-nums font-mono">{duration}</span>
        ) : null}
      </button>

      {expanded && (
        <div className="border-t border-[hsl(var(--border))]/30 text-xs animate-fade-in">
          {isStreaming ? renderStreamingContent(part, streamingArgs) : renderToolContent(part)}
        </div>
      )}
    </div>
  )
})

function getToolTitle(part: ToolPartData): string {
  const input = part.input || {}
  switch (part.tool) {
    case "bash":
      return String(input.command || "").slice(0, 80)
    case "read":
      return String(input.file_path || input.path || "")
    case "write":
      return String(input.file_path || input.path || "")
    case "edit":
      return String(input.file_path || input.path || "")
    case "glob":
      return String(input.pattern || "")
    case "grep":
      return `${input.pattern || ""} ${input.path || ""}`
    case "task":
      return String(input.description || "")
    default:
      return JSON.stringify(input).slice(0, 60)
  }
}

function renderToolContent(part: ToolPartData) {
  switch (part.tool) {
    case "bash":
      return <ToolBash input={part.input} output={part.output} error={part.error} status={part.status} />
    case "read":
      return <ToolRead input={part.input} output={part.output} />
    case "edit":
    case "write":
    case "apply_patch":
      return <ToolEdit input={part.input} output={part.output} />
    case "grep":
      return <ToolGrep input={part.input} output={part.output} />
    case "glob":
      return <ToolGlob input={part.input} output={part.output} />
    case "task":
      return <ToolTask input={part.input} output={part.output} status={part.status} />
    default:
      return <DefaultToolContent input={part.input} output={part.output} error={part.error} />
  }
}

function getStreamingTitle(_part: ToolPartData, raw?: string): string {
  // Try to extract file_path from partial JSON
  if (raw) {
    const pathMatch = raw.match(/"file_path"\s*:\s*"([^"]*)"/)
    if (pathMatch) return pathMatch[1]
    const commandMatch = raw.match(/"command"\s*:\s*"([^"]*)"/)
    if (commandMatch) return commandMatch[1].slice(0, 80)
  }
  return "Generating..."
}

function renderStreamingContent(_part: ToolPartData, raw?: string) {
  if (!raw) return null

  // Try to extract meaningful content from the partial JSON args
  // For write/edit tools, extract the content/new_string being generated
  const contentMatch = raw.match(/"(?:content|new_string)"\s*:\s*"((?:[^"\\]|\\.)*)/)
  if (contentMatch) {
    // Unescape JSON string escapes
    let content: string
    try {
      content = JSON.parse(`"${contentMatch[1]}"`)
    } catch {
      content = contentMatch[1].replace(/\\n/g, "\n").replace(/\\t/g, "\t").replace(/\\"/g, '"')
    }
    return (
      <div className="font-mono text-[11px]">
        <div className="px-3.5 py-2.5 overflow-x-auto max-h-64 overflow-y-auto bg-[hsl(var(--terminal-bg))]">
          <pre className="whitespace-pre-wrap leading-relaxed text-[hsl(var(--success))]/80">{content}<span className="animate-pulse">|</span></pre>
        </div>
      </div>
    )
  }

  // For other tools, show raw JSON being built
  return (
    <div className="p-3.5 font-mono text-[11px] bg-[hsl(var(--terminal-bg))]">
      <pre className="whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto leading-relaxed text-[hsl(var(--muted-foreground))]/70">{raw}<span className="animate-pulse">|</span></pre>
    </div>
  )
}

function DefaultToolContent({ input, output, error }: { input?: Record<string, unknown>; output?: string; error?: string }) {
  return (
    <div className="p-3.5 space-y-2.5 font-mono bg-[hsl(var(--terminal-bg))]">
      {input && Object.keys(input).length > 0 && (
        <div>
          <div className="text-[hsl(var(--muted-foreground))]/70 mb-1.5 text-[10px] font-mono uppercase tracking-wider">Input</div>
          <pre className="text-[11px] whitespace-pre-wrap overflow-x-auto leading-relaxed">{JSON.stringify(input, null, 2)}</pre>
        </div>
      )}
      {error && <div className="text-[hsl(var(--destructive))] rounded-sm bg-[hsl(var(--destructive))]/5 px-2.5 py-1.5 glow-coral">{error}</div>}
      {output && (
        <div>
          <div className="text-[hsl(var(--muted-foreground))]/70 mb-1.5 text-[10px] font-mono uppercase tracking-wider">Output</div>
          <pre className="text-[11px] whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto leading-relaxed">{output}</pre>
        </div>
      )}
    </div>
  )
}
