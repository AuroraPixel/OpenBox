import { FileText } from "lucide-react"

interface PlanBannerProps {
  planPath?: string
}

export function PlanBanner({ planPath }: PlanBannerProps) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 bg-[hsl(var(--primary))]/8 border-b border-[hsl(var(--primary))]/20 text-[hsl(var(--primary))] text-sm shrink-0 glow-cyan">
      <div className="h-6 w-6 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center">
        <FileText className="h-3.5 w-3.5" />
      </div>
      <span className="font-display uppercase tracking-wider">Plan Mode</span>
      <span className="text-[hsl(var(--primary))]/50 font-mono uppercase tracking-wider text-[10px]">&mdash; Read Only</span>
      {planPath && (
        <span className="text-[hsl(var(--primary))]/30 text-xs truncate max-w-[300px] font-mono">{planPath}</span>
      )}
    </div>
  )
}
