import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface SpinnerProps {
  size?: "sm" | "md" | "lg"
  className?: string
}

const sizes = { sm: "h-3.5 w-3.5", md: "h-5 w-5", lg: "h-8 w-8" }

export function Spinner({ size = "md", className }: SpinnerProps) {
  return <Loader2 className={cn("animate-spin text-[hsl(var(--primary))] glow-cyan drop-shadow-[0_0_6px_hsl(var(--primary)/0.5)]", sizes[size], className)} />
}
