import { useState } from "react"
import { ChevronDown, ChevronRight, FilePlus, FileEdit, FileMinus } from "lucide-react"
import { cn } from "@/lib/utils"
import type { DiffEntry, DiffHunk, DiffLine } from "@/types"

interface DiffFileProps {
  entry: DiffEntry
  viewMode: "unified" | "split"
}

const statusIcon = {
  added: <FilePlus className="h-3.5 w-3.5 text-[hsl(var(--success))]" />,
  modified: <FileEdit className="h-3.5 w-3.5 text-[hsl(var(--accent))]" />,
  deleted: <FileMinus className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" />,
}

function UnifiedView({ hunks }: { hunks: DiffHunk[] }) {
  return (
    <div className="overflow-x-auto font-mono text-[11px] leading-relaxed">
      {hunks.map((hunk, i) => (
        <div key={i}>
          <div className="px-3 py-1.5 bg-[hsl(var(--muted))]/30 text-[hsl(var(--muted-foreground))] text-[10px] font-mono uppercase tracking-wider border-y border-[hsl(var(--border))]/30">
            @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
          </div>
          {hunk.lines.map((line, j) => (
            <div
              key={j}
              className={cn(
                "px-3 py-px flex",
                line.type === "add" && "bg-[hsl(var(--success))]/8 border-l-2 border-[hsl(var(--success))]/40",
                line.type === "del" && "bg-[hsl(var(--destructive))]/8 border-l-2 border-[hsl(var(--destructive))]/40",
                line.type === "context" && "border-l-2 border-transparent",
              )}
            >
              <span className="w-10 text-right pr-2 text-[hsl(var(--muted-foreground))]/60 select-none shrink-0 tabular-nums">
                {line.old_line || ""}
              </span>
              <span className="w-10 text-right pr-2 text-[hsl(var(--muted-foreground))]/60 select-none shrink-0 tabular-nums">
                {line.new_line || ""}
              </span>
              <span className={cn(
                "w-4 text-center select-none shrink-0 font-bold",
                line.type === "add" && "text-[hsl(var(--success))]",
                line.type === "del" && "text-[hsl(var(--destructive))]",
              )}>
                {line.type === "add" ? "+" : line.type === "del" ? "-" : " "}
              </span>
              <span className="flex-1">{line.content}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

interface SplitRow {
  left: DiffLine | null
  right: DiffLine | null
}

function buildSplitRows(lines: DiffLine[]): SplitRow[] {
  const rows: SplitRow[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.type === "context") {
      rows.push({ left: line, right: line })
      i++
    } else if (line.type === "del") {
      // Collect consecutive deletes then pair with consecutive adds
      const dels: DiffLine[] = []
      while (i < lines.length && lines[i].type === "del") {
        dels.push(lines[i])
        i++
      }
      const adds: DiffLine[] = []
      while (i < lines.length && lines[i].type === "add") {
        adds.push(lines[i])
        i++
      }
      const max = Math.max(dels.length, adds.length)
      for (let k = 0; k < max; k++) {
        rows.push({
          left: k < dels.length ? dels[k] : null,
          right: k < adds.length ? adds[k] : null,
        })
      }
    } else if (line.type === "add") {
      rows.push({ left: null, right: line })
      i++
    } else {
      i++
    }
  }
  return rows
}

function SplitView({ hunks }: { hunks: DiffHunk[] }) {
  return (
    <div className="overflow-x-auto font-mono text-[11px] leading-relaxed">
      {hunks.map((hunk, i) => (
        <div key={i}>
          <div className="px-3 py-1.5 bg-[hsl(var(--muted))]/30 text-[hsl(var(--muted-foreground))] text-[10px] font-mono uppercase tracking-wider border-y border-[hsl(var(--border))]/30">
            @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
          </div>
          <div className="grid grid-cols-2 divide-x divide-[hsl(var(--border))]/50">
            {buildSplitRows(hunk.lines).map((row, j) => (
              <SplitRowPair key={j} row={row} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function SplitRowPair({ row }: { row: SplitRow }) {
  return (
    <>
      {/* Left side (old) */}
      <div className={cn(
        "px-2 py-px flex min-h-[20px]",
        row.left?.type === "del" && "bg-[hsl(var(--destructive))]/8",
        !row.left && "bg-[hsl(var(--muted))]/10",
      )}>
        <span className="w-8 text-right pr-2 text-[hsl(var(--muted-foreground))]/60 select-none shrink-0 tabular-nums">
          {row.left?.old_line || ""}
        </span>
        <span className={cn(
          "w-3 text-center select-none shrink-0 font-bold",
          row.left?.type === "del" && "text-[hsl(var(--destructive))]",
        )}>
          {row.left?.type === "del" ? "-" : row.left?.type === "context" ? " " : ""}
        </span>
        <span className="flex-1 break-all">{row.left?.content ?? ""}</span>
      </div>
      {/* Right side (new) */}
      <div className={cn(
        "px-2 py-px flex min-h-[20px]",
        row.right?.type === "add" && "bg-[hsl(var(--success))]/8",
        !row.right && "bg-[hsl(var(--muted))]/10",
      )}>
        <span className="w-8 text-right pr-2 text-[hsl(var(--muted-foreground))]/60 select-none shrink-0 tabular-nums">
          {row.right?.new_line || ""}
        </span>
        <span className={cn(
          "w-3 text-center select-none shrink-0 font-bold",
          row.right?.type === "add" && "text-[hsl(var(--success))]",
        )}>
          {row.right?.type === "add" ? "+" : row.right?.type === "context" ? " " : ""}
        </span>
        <span className="flex-1 break-all">{row.right?.content ?? ""}</span>
      </div>
    </>
  )
}

export function DiffFile({ entry, viewMode }: DiffFileProps) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="rounded-sm border border-[hsl(var(--border))]/50 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm bg-[hsl(var(--muted))]/20 hover:bg-[hsl(var(--muted))]/40 transition-colors cursor-pointer"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]" /> : <ChevronRight className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]" />}
        {statusIcon[entry.status]}
        <span className="font-mono text-xs flex-1 text-left truncate">{entry.path}</span>
        <div className="flex items-center gap-2.5 text-xs shrink-0 tabular-nums font-mono font-medium">
          {entry.additions > 0 && <span className="text-[hsl(var(--success))] bg-[hsl(var(--success))]/10 px-1.5 py-0.5 rounded-sm">+{entry.additions}</span>}
          {entry.deletions > 0 && <span className="text-[hsl(var(--destructive))] bg-[hsl(var(--destructive))]/10 px-1.5 py-0.5 rounded-sm">-{entry.deletions}</span>}
        </div>
      </button>
      {expanded && entry.hunks && (
        viewMode === "split"
          ? <SplitView hunks={entry.hunks} />
          : <UnifiedView hunks={entry.hunks} />
      )}
    </div>
  )
}
