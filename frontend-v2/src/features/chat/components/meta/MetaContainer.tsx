// Hover-revealed strip that carries a message's meta badges and action icons.
// Desktop: hidden until the parent `group/msg` is hovered or focused within.
// Coarse pointers (touch) can't hover, so it stays visible there.
import { useMemo, type PropsWithChildren } from "react"
import { cn } from "@/shared/lib/cn"

function useCoarsePointer(): boolean {
  return useMemo(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(pointer: coarse)").matches,
    [],
  )
}

export function MetaContainer({
  align,
  children,
}: PropsWithChildren<{ align: "start" | "end" }>) {
  const coarse = useCoarsePointer()
  return (
    <div
      className={cn(
        "text-n600 mt-1.5 flex items-center gap-1 text-xs transition-opacity duration-150",
        align === "end" ? "justify-end" : "justify-start",
        coarse
          ? "opacity-100"
          : "md:pointer-events-none md:opacity-0 md:group-hover/msg:pointer-events-auto md:group-hover/msg:opacity-100 md:group-focus-within/msg:pointer-events-auto md:group-focus-within/msg:opacity-100",
      )}
    >
      {children}
    </div>
  )
}
