import { GitBranch } from "lucide-react"
import type { DiffEntry } from "@/types"

interface DiffSummaryProps {
  entries: DiffEntry[]
  viewMode: "unified" | "split"
  onViewModeChange: (mode: "unified" | "split") => void
}

export function DiffSummary({ entries, viewMode, onViewModeChange }: DiffSummaryProps) {
  const totalAdd = entries.reduce((s, e) => s + e.additions, 0)
  const totalDel = entries.reduce((s, e) => s + e.deletions, 0)

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]">
      <div className="flex items-center gap-3 text-sm">
        <div className="h-7 w-7 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
          <GitBranch className="h-3.5 w-3.5 text-[hsl(var(--primary))]" />
        </div>
        <span className="font-mono font-medium tabular-nums">{entries.length} file{entries.length !== 1 ? "s" : ""} changed</span>
        {totalAdd > 0 && <span className="text-[hsl(var(--success))] bg-[hsl(var(--success))]/10 px-2 py-0.5 rounded-sm text-xs font-mono font-medium tabular-nums">+{totalAdd}</span>}
        {totalDel > 0 && <span className="text-[hsl(var(--destructive))] bg-[hsl(var(--destructive))]/10 px-2 py-0.5 rounded-sm text-xs font-mono font-medium tabular-nums">-{totalDel}</span>}
      </div>
      <div className="flex rounded-sm border border-[hsl(var(--border))]/50 overflow-hidden">
        <button
          onClick={() => onViewModeChange("unified")}
          className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider cursor-pointer transition-all ${viewMode === "unified" ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] glow-cyan" : "hover:bg-[hsl(var(--muted))]/50 text-[hsl(var(--muted-foreground))]"}`}
        >
          Unified
        </button>
        <button
          onClick={() => onViewModeChange("split")}
          className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider cursor-pointer transition-all border-l border-[hsl(var(--border))]/50 ${viewMode === "split" ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] glow-cyan" : "hover:bg-[hsl(var(--muted))]/50 text-[hsl(var(--muted-foreground))]"}`}
        >
          Split
        </button>
      </div>
    </div>
  )
}
