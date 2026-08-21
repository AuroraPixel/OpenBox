import { cn } from "@/shared/lib/cn"

interface BrandMarkProps {
  size?: "sm" | "md"
  withWordmark?: boolean
  className?: string
}

/** The "b" tile + shining wordmark from the design. */
export function BrandMark({ size = "md", withWordmark = true, className }: BrandMarkProps) {
  const tile = size === "sm" ? "size-6.5 rounded-lg" : "size-7 rounded-[9px]"
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <span className={cn("relative flex flex-none items-center justify-center bg-ink", tile)}>
        <span className="mt-px text-lg leading-none font-bold text-bg">b</span>
        <span className="absolute -end-px -top-px size-1.75 rounded-full bg-a300 shadow-[0_0_0_2px_var(--t-rail)]" />
      </span>
      {withWordmark && (
        <span className="wordmark truncate text-xl leading-none font-bold tracking-tighter">bossip</span>
      )}
    </span>
  )
}
