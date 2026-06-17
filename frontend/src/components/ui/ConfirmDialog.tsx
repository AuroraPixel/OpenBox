import { useEffect, useRef } from "react"
import { AlertTriangle } from "lucide-react"
import { cn } from "@/lib/utils"

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: "danger" | "default"
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [open, onCancel])

  // Focus trap
  useEffect(() => {
    if (open) dialogRef.current?.focus()
  }, [open])

  if (!open) return null

  const isDanger = variant === "danger"

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onCancel} />

      {/* Dialog */}
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="relative z-10 max-w-sm w-full mx-4 p-5 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-sm shadow-xl animate-slide-up outline-none"
      >
        <div className="flex items-start gap-3 mb-4">
          {isDanger && (
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--destructive))]/10 flex items-center justify-center shrink-0 glow-coral">
              <AlertTriangle className="h-4.5 w-4.5 text-[hsl(var(--destructive))]" />
            </div>
          )}
          <div>
            <h3 className="text-sm font-mono uppercase tracking-wider font-semibold text-[hsl(var(--foreground))]">
              {title}
            </h3>
            <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono mt-1.5 leading-relaxed">
              {message}
            </p>
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 transition-all cursor-pointer"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={cn(
              "px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              isDanger
                ? "bg-[hsl(var(--destructive))] text-white hover:opacity-90 glow-coral"
                : "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 glow-cyan",
            )}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
