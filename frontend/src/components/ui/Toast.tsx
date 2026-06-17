import { useState, useCallback, useEffect, createContext, useContext } from "react"
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from "lucide-react"
import { cn } from "@/lib/utils"

type ToastType = "success" | "error" | "info" | "warning"

interface Toast {
  id: string
  type: ToastType
  message: string
}

interface ToastContextValue {
  addToast: (type: ToastType, message: string) => void
}

const ToastContext = createContext<ToastContextValue>({ addToast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

const icons: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
  warning: AlertTriangle,
}

const colors: Record<ToastType, { bg: string; icon: string }> = {
  success: { bg: "bg-[hsl(var(--card))] border-[hsl(var(--success))]/30 shadow-[0_0_12px_hsl(var(--success)/0.15)]", icon: "text-[hsl(var(--success))] glow-green" },
  error: { bg: "bg-[hsl(var(--card))] border-[hsl(var(--destructive))]/30 shadow-[0_0_12px_hsl(var(--destructive)/0.15)]", icon: "text-[hsl(var(--destructive))] glow-coral" },
  info: { bg: "bg-[hsl(var(--card))] border-[hsl(var(--primary))]/30 shadow-[0_0_12px_hsl(var(--primary)/0.15)]", icon: "text-[hsl(var(--primary))] glow-cyan" },
  warning: { bg: "bg-[hsl(var(--card))] border-[hsl(var(--accent))]/30 shadow-[0_0_12px_hsl(var(--accent)/0.15)]", icon: "text-[hsl(var(--accent))] glow-amber" },
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, message: string) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts((prev) => [...prev, { id, type, message }])
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2.5 max-w-sm">
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={removeToast} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const Icon = icons[toast.type]
  const color = colors[toast.type]

  useEffect(() => {
    const timer = setTimeout(() => onRemove(toast.id), 4000)
    return () => clearTimeout(timer)
  }, [toast.id, onRemove])

  return (
    <div className={cn(
      "flex items-start gap-3 px-4 py-3 rounded-sm border animate-slide-up",
      color.bg,
    )}>
      <Icon className={cn("h-4 w-4 mt-0.5 shrink-0", color.icon)} />
      <p className="text-sm flex-1 font-mono text-[hsl(var(--foreground))]">{toast.message}</p>
      <button
        onClick={() => onRemove(toast.id)}
        className="p-0.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
        aria-label="Dismiss notification"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}
