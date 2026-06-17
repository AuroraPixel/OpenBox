import { cn } from "@/lib/utils"

type BadgeVariant = "default" | "success" | "warning" | "error" | "info" | "outline"

interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  className?: string
}

const variants: Record<BadgeVariant, string> = {
  default: "bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))]",
  success: "bg-[hsl(var(--success))]/10 text-[hsl(var(--success))] border border-[hsl(var(--success))]/20 shadow-[0_0_6px_hsl(var(--success)/0.3)]",
  warning: "bg-[hsl(var(--accent))]/10 text-[hsl(var(--accent))] border border-[hsl(var(--accent))]/20 shadow-[0_0_6px_hsl(var(--accent)/0.3)]",
  error: "bg-[hsl(var(--destructive))]/10 text-[hsl(var(--destructive))] border border-[hsl(var(--destructive))]/20 shadow-[0_0_6px_hsl(var(--destructive)/0.3)]",
  info: "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/20 shadow-[0_0_6px_hsl(var(--primary)/0.3)]",
  outline: "border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))]",
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-mono uppercase tracking-wider rounded-sm",
      variants[variant],
      className,
    )}>
      {children}
    </span>
  )
}
