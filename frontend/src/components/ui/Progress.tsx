import { cn } from "@/lib/utils"

interface ProgressProps {
  value: number
  max?: number
  className?: string
  color?: string
  showLabel?: boolean
}

export function Progress({ value, max = 100, className, color, showLabel }: ProgressProps) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = color || (percent > 80 ? "bg-[hsl(var(--destructive))] shadow-[0_0_8px_hsl(var(--destructive)/0.4)]" : percent > 60 ? "bg-[hsl(var(--accent))] shadow-[0_0_8px_hsl(var(--accent)/0.4)]" : "bg-[hsl(var(--primary))] shadow-[0_0_8px_hsl(var(--primary)/0.4)]")

  return (
    <div className={cn("w-full", className)}>
      <div className="h-1.5 rounded-sm bg-[hsl(var(--muted))] overflow-hidden border border-[hsl(var(--border))]">
        <div
          className={cn("h-full rounded-sm transition-all duration-500 ease-out", barColor)}
          style={{ width: `${percent}%` }}
        />
      </div>
      {showLabel && (
        <div className="text-[10px] text-[hsl(var(--muted-foreground))] mt-1 text-right font-mono uppercase tracking-wider tabular-nums">
          {percent.toFixed(1)}%
        </div>
      )}
    </div>
  )
}
