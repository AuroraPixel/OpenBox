import { cn } from "@/shared/lib/cn"

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-4 animate-spin-arc rounded-full border-2 border-n300 border-t-a700",
        className,
      )}
      role="status"
    />
  )
}
