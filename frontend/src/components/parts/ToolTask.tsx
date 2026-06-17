import { Bot, ChevronRight, ChevronDown } from "lucide-react"
import { useState } from "react"
import type { ToolStatus } from "@/types"

interface ToolTaskProps {
  input?: Record<string, unknown>
  output?: string
  status: ToolStatus
}

export function ToolTask({ input, output }: ToolTaskProps) {
  const [expanded, setExpanded] = useState(false)
  const agentType = String(input?.subagent_type || input?.agent || "agent")
  const description = String(input?.description || input?.prompt || "")

  return (
    <div className="text-[11px]">
      <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] flex items-center gap-2.5">
        <div className="flex items-center justify-center h-5 w-5 rounded-sm bg-[hsl(var(--primary))]/10 shadow-[0_0_6px_hsl(var(--primary)/0.3)]">
          <Bot className="h-3 w-3 text-[hsl(var(--primary))] glow-cyan" />
        </div>
        <span className="font-mono uppercase tracking-wider font-medium text-[hsl(var(--primary))]">{agentType}</span>
        <span className="text-[hsl(var(--muted-foreground))] truncate font-mono">{description.slice(0, 80)}</span>
      </div>
      {output && (
        <div className="px-3.5 py-1.5 bg-[hsl(var(--terminal-bg))]">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] cursor-pointer transition-colors font-mono uppercase tracking-wider"
          >
            {expanded ? <ChevronDown className="h-3 w-3 opacity-60" /> : <ChevronRight className="h-3 w-3 opacity-60" />}
            Show subtask output
          </button>
          {expanded && (
            <pre className="mt-1.5 whitespace-pre-wrap overflow-x-auto max-h-48 overflow-y-auto text-[hsl(var(--muted-foreground))]/80 leading-relaxed animate-fade-in font-mono">
              {output}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
