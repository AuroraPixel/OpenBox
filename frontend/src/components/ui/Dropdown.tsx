import { useState, useRef, useEffect } from "react"
import { ChevronDown, Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface DropdownOption {
  value: string
  label: string
  description?: string
}

interface DropdownProps {
  options: DropdownOption[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  size?: "sm" | "md"
}

export function Dropdown({ options, value, onChange, placeholder, className, size = "sm" }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const selected = options.find((o) => o.value === value)

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] transition-all cursor-pointer font-mono",
          "hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--muted-foreground))]/20",
          open && "ring-1 ring-[hsl(var(--primary))]/30 border-[hsl(var(--primary))]/20 shadow-[0_0_8px_hsl(var(--primary)/0.15)]",
          size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
        )}
      >
        <span className="truncate text-[hsl(var(--foreground))]">{selected?.label || placeholder || "Select..."}</span>
        <ChevronDown className={cn("h-3 w-3 text-[hsl(var(--muted-foreground))] transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1.5 z-50 min-w-[180px] rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-[0_4px_24px_hsl(var(--background)/0.6)] py-1 animate-fade-in">
          {options.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { onChange(opt.value); setOpen(false) }}
              className={cn(
                "w-full flex items-center gap-2 text-left px-3 py-2 text-sm font-mono transition-colors cursor-pointer",
                "hover:bg-[hsl(var(--muted))]",
                opt.value === value && "text-[hsl(var(--primary))] glow-cyan",
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate">{opt.label}</div>
                {opt.description && (
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] truncate">{opt.description}</div>
                )}
              </div>
              {opt.value === value && <Check className="h-3.5 w-3.5 shrink-0 text-[hsl(var(--primary))]" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
