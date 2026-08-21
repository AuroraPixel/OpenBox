import { useEffect, useRef, type ReactNode } from "react"
import { cn } from "@/shared/lib/cn"

interface MenuProps {
  open: boolean
  onClose: () => void
  className?: string
  children: ReactNode
}

/** Floating menu card. Position it with className (absolute + offsets). */
export function Menu({ open, onClose, className, children }: MenuProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    // Defer so the opening click doesn't immediately close it.
    const id = window.setTimeout(() => window.addEventListener("mousedown", onDown), 0)
    window.addEventListener("keydown", onKey)
    return () => {
      window.clearTimeout(id)
      window.removeEventListener("mousedown", onDown)
      window.removeEventListener("keydown", onKey)
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      ref={ref}
      className={cn(
        "absolute z-30 flex flex-col rounded-xl border border-hair bg-card p-1.5 shadow-pop",
        className,
      )}
      role="menu"
    >
      {children}
    </div>
  )
}

interface MenuItemProps {
  onClick: () => void
  danger?: boolean
  children: ReactNode
}

export function MenuItem({ onClick, danger, children }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-2 text-start text-md hover:bg-n200",
        danger ? "text-danger" : "text-ink",
      )}
    >
      {children}
    </button>
  )
}
