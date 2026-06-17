import { useState } from "react"
import { Copy, Check } from "lucide-react"
import type { ToolStatus } from "@/types"

interface ToolBashProps {
  input?: Record<string, unknown>
  output?: string
  error?: string
  status: ToolStatus
}

export function ToolBash({ input, output, error }: ToolBashProps) {
  const [copied, setCopied] = useState(false)
  const command = String(input?.command || "")
  const lines = (output || "").split("\n")
  const maxLines = 20
  const truncated = lines.length > maxLines

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(output || "")
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }

  return (
    <div className="font-mono text-[11px]">
      {command && (
        <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] text-[hsl(var(--muted-foreground))]">
          <span className="text-[hsl(var(--success))] font-medium glow-green">$</span> {command}
        </div>
      )}
      {error && (
        <div className="px-3.5 py-2.5 text-[hsl(var(--destructive))] whitespace-pre-wrap bg-[hsl(var(--destructive))]/5 glow-coral">{error}</div>
      )}
      {output && (
        <div className="px-3.5 py-2.5 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto relative group leading-relaxed bg-[hsl(var(--terminal-bg))] text-[hsl(var(--terminal-fg))]">
          {truncated ? lines.slice(0, maxLines).join("\n") : output}
          {truncated && (
            <div className="mt-1.5 text-[hsl(var(--muted-foreground))]/60 tabular-nums font-mono uppercase tracking-wider">
              ... {lines.length - maxLines} more lines
            </div>
          )}
          <button
            onClick={handleCopy}
            className="absolute top-1.5 right-1.5 p-1.5 rounded-sm bg-[hsl(var(--muted))]/80 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:bg-[hsl(var(--accent))]/60 shadow-[0_0_6px_hsl(var(--accent)/0.2)] backdrop-blur-sm"
            aria-label="Copy output"
          >
            {copied ? <Check className="h-3 w-3 text-[hsl(var(--success))] glow-green" /> : <Copy className="h-3 w-3" />}
          </button>
        </div>
      )}
    </div>
  )
}
