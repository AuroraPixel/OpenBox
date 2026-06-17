import { FilePlus, FileMinus, FileEdit } from "lucide-react"
import type { PatchFile } from "@/types"

interface PatchPartProps {
  files: PatchFile[]
}

const statusIcons = {
  added: <FilePlus className="h-3.5 w-3.5 text-[hsl(var(--success))] glow-green" />,
  modified: <FileEdit className="h-3.5 w-3.5 text-[hsl(var(--accent))] glow-amber" />,
  deleted: <FileMinus className="h-3.5 w-3.5 text-[hsl(var(--destructive))] glow-coral" />,
}

export function PatchPart({ files }: PatchPartProps) {
  const totalAdd = files.reduce((s, f) => s + f.additions, 0)
  const totalDel = files.reduce((s, f) => s + f.deletions, 0)

  return (
    <div className="rounded-sm border border-[hsl(var(--border))]/50 overflow-hidden shadow-[0_0_6px_hsl(var(--primary)/0.1)]">
      <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] flex items-center gap-3 text-xs">
        <span className="font-mono uppercase tracking-wider font-medium tabular-nums">{files.length} file{files.length !== 1 ? "s" : ""} changed</span>
        {totalAdd > 0 && <span className="text-[hsl(var(--success))] font-mono tabular-nums glow-green">+{totalAdd}</span>}
        {totalDel > 0 && <span className="text-[hsl(var(--destructive))] font-mono tabular-nums glow-coral">-{totalDel}</span>}
      </div>
      <div className="divide-y divide-[hsl(var(--border))]/30">
        {files.map((file) => (
          <div key={file.path} className="flex items-center gap-2.5 px-3.5 py-2 text-xs hover:bg-[hsl(var(--surface-1))] transition-colors cursor-pointer">
            {statusIcons[file.status]}
            <span className="font-mono truncate flex-1 text-[hsl(var(--accent))]">{file.path}</span>
            <span className="flex items-center gap-2 shrink-0 font-mono tabular-nums">
              {file.additions > 0 && <span className="text-[hsl(var(--success))]">+{file.additions}</span>}
              {file.deletions > 0 && <span className="text-[hsl(var(--destructive))]">-{file.deletions}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
