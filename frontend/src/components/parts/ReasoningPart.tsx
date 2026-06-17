import { useState } from "react"
import { ChevronRight, ChevronDown, Brain } from "lucide-react"

interface ReasoningPartProps {
  text: string
  isStreaming?: boolean
}

export function ReasoningPart({ text, isStreaming }: ReasoningPartProps) {
  const [expanded, setExpanded] = useState(false)

  if (!text) return null

  return (
    <div className="rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--card))] overflow-hidden shadow-[0_0_6px_hsl(var(--primary)/0.08)]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--surface-1))] transition-colors cursor-pointer"
      >
        {expanded ? <ChevronDown className="h-3 w-3 opacity-60" /> : <ChevronRight className="h-3 w-3 opacity-60" />}
        <div className="flex items-center justify-center h-5 w-5 rounded-sm bg-violet-500/10 shadow-[0_0_6px_hsl(270_60%_60%/0.3)]">
          <Brain className="h-3 w-3 text-violet-400" />
        </div>
        <span className="font-mono uppercase tracking-wider italic">Thinking{isStreaming ? "" : "..."}</span>
        {isStreaming && (
          <span className="flex items-center gap-0.5 ml-0.5">
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" />
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" style={{ animationDelay: "0.15s" }} />
            <span className="h-1 w-1 rounded-full bg-current animate-pulse" style={{ animationDelay: "0.3s" }} />
          </span>
        )}
        {!expanded && (
          <span className="ml-1 truncate max-w-[300px] opacity-50 font-mono">{text.slice(0, 80)}...</span>
        )}
      </button>
      {expanded && (
        <div className="px-3.5 pb-3.5 text-sm font-mono text-[hsl(var(--muted-foreground))]/80 italic whitespace-pre-wrap animate-fade-in leading-relaxed">
          {text}
        </div>
      )}
    </div>
  )
}
