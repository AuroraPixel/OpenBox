import { useState } from "react"
import { Layers, ChevronDown, ChevronRight } from "lucide-react"

interface CompactionBadgeProps {
  summary?: string
}

export function CompactionBadge({ summary }: CompactionBadgeProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="rounded-sm bg-[hsl(var(--card))] border border-[hsl(var(--compaction-banner))]/20 overflow-hidden shadow-[0_0_6px_hsl(var(--compaction-banner)/0.15)]">
      <button
        onClick={() => summary && setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-xs text-[hsl(var(--compaction-banner))] cursor-pointer hover:bg-[hsl(var(--surface-1))] transition-colors"
      >
        <div className="flex items-center justify-center h-5 w-5 rounded-sm bg-[hsl(var(--compaction-banner))]/10 shadow-[0_0_6px_hsl(var(--compaction-banner)/0.3)]">
          <Layers className="h-3 w-3" />
        </div>
        <span className="font-mono uppercase tracking-wider font-medium">Context compacted</span>
        {summary && (expanded ? <ChevronDown className="h-3 w-3 ml-auto opacity-60" /> : <ChevronRight className="h-3 w-3 ml-auto opacity-60" />)}
      </button>
      {expanded && summary && (
        <div className="px-3.5 pb-3 text-xs font-mono text-[hsl(var(--muted-foreground))] whitespace-pre-wrap animate-fade-in">
          {summary}
        </div>
      )}
    </div>
  )
}
