import { useState } from "react"
import { cn } from "@/lib/utils"

interface TooltipProps {
  content: string
  children: React.ReactNode
  side?: "top" | "bottom"
  className?: string
}

export function Tooltip({ content, children, side = "top", className }: TooltipProps) {
  const [show, setShow] = useState(false)

  return (
    <div
      className="relative inline-flex"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <div className={cn(
          "absolute z-50 px-2.5 py-1 text-[11px] font-mono uppercase tracking-wider rounded-sm shadow-[0_0_12px_hsl(var(--primary)/0.15)] pointer-events-none",
          "bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--primary))]/20 whitespace-nowrap",
          side === "top" ? "bottom-full mb-2 left-1/2 -translate-x-1/2" : "top-full mt-2 left-1/2 -translate-x-1/2",
          className,
        )}>
          {content}
        </div>
      )}
    </div>
  )
}
