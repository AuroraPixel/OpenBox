// Hover/focus tooltip used by the message meta badges. Positioned with a
// fixed-coordinate portal so it escapes the chat column's overflow clipping.
import { useCallback, useId, useRef, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"
import { cn } from "@/shared/lib/cn"

interface Props {
  label: ReactNode
  side?: "top" | "bottom"
  className?: string
  children: ReactNode
}

export function Tooltip({ label, side = "top", className, children }: Props) {
  const id = useId()
  const ref = useRef<HTMLSpanElement>(null)
  const [box, setBox] = useState<{ x: number; y: number } | null>(null)

  const show = useCallback(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setBox({ x: r.left + r.width / 2, y: side === "top" ? r.top : r.bottom })
  }, [side])

  const hide = useCallback(() => setBox(null), [])

  return (
    <>
      <span
        ref={ref}
        className={cn("inline-flex", className)}
        aria-describedby={box ? id : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        {children}
      </span>
      {box &&
        createPortal(
          <span
            id={id}
            role="tooltip"
            className="border-hair bg-card text-ink shadow-pop pointer-events-none fixed z-70 -translate-x-1/2 rounded-md border px-2 py-1 text-xs whitespace-nowrap"
            style={{
              left: box.x,
              top: box.y,
              transform: side === "top" ? "translate(-50%, calc(-100% - 6px))" : "translate(-50%, 6px)",
            }}
          >
            {label}
          </span>,
          document.body,
        )}
    </>
  )
}
