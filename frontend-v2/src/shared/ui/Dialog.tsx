import { useEffect, type ReactNode } from "react"
import { createPortal } from "react-dom"

interface DialogProps {
  open: boolean
  onClose: () => void
  children: ReactNode
}

/** Design-language modal shell: dim scrim + 400px rounded card. */
export function Dialog({ open, onClose, children }: DialogProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-n900/30"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex w-100 max-w-[calc(100vw-2rem)] flex-col gap-2.5 rounded-2xl border border-hair bg-card p-6.5 shadow-pop"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function DialogTitle({ children }: { children: ReactNode }) {
  return <span className="text-2xl font-medium tracking-tight">{children}</span>
}

export function DialogBody({ children }: { children: ReactNode }) {
  return <span className="text-base leading-relaxed text-n700">{children}</span>
}

export function DialogActions({ children }: { children: ReactNode }) {
  return <div className="mt-3 flex items-center justify-end gap-4.5">{children}</div>
}
