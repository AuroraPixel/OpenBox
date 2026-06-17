import { useEffect, useRef } from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  className?: string
  showClose?: boolean
}

export function Modal({ open, onClose, title, children, className, showClose = true }: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4">
      <div
        ref={overlayRef}
        className="absolute inset-0 bg-[hsl(var(--background))]/80 backdrop-blur-sm scanlines"
        onClick={onClose}
      />
      <div className={cn(
        "relative bg-[hsl(var(--card))] rounded-t-lg sm:rounded-sm border-t sm:border border-[hsl(var(--primary))]/20 shadow-[0_0_30px_hsl(var(--primary)/0.1)] max-h-[90vh] sm:max-h-[85vh] overflow-hidden flex flex-col animate-slide-up w-full",
        className || "sm:w-[480px]",
      )}>
        {(title || showClose) && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--border))]">
            {title && <h2 className="text-base font-display font-semibold text-[hsl(var(--foreground))] glow-cyan">{title}</h2>}
            {showClose && (
              <button
                onClick={onClose}
                className="p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}
