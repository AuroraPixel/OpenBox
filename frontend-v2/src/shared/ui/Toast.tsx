// Minimal toast host — one of the ≤3 global stores (auth, appearance, toast).
import { create } from "zustand"
import { cn } from "@/shared/lib/cn"

type ToastKind = "info" | "error"
interface ToastItem {
  id: number
  kind: ToastKind
  text: string
}

interface ToastState {
  items: ToastItem[]
  push: (kind: ToastKind, text: string) => void
  remove: (id: number) => void
}

let seq = 0

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (kind, text) => {
    const id = ++seq
    set((s) => ({ items: [...s.items, { id, kind, text }] }))
    window.setTimeout(() => set((s) => ({ items: s.items.filter((t) => t.id !== id) })), 3200)
  },
  remove: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}))

export function toast(kind: ToastKind, text: string): void {
  useToastStore.getState().push(kind, text)
}

export function ToastHost() {
  const items = useToastStore((s) => s.items)
  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-60 flex -translate-x-1/2 flex-col items-center gap-2">
      {items.map((t) => (
        <div
          key={t.id}
          role="status"
          className={cn(
            "pointer-events-auto animate-fade-up rounded-full border px-4.5 py-2 text-md shadow-pop",
            t.kind === "error"
              ? "border-hair bg-card text-danger"
              : "border-hair bg-card text-ink",
          )}
        >
          {t.text}
        </div>
      ))}
    </div>
  )
}
