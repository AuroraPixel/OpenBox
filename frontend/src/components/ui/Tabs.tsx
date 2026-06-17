import { cn } from "@/lib/utils"

interface Tab {
  id: string
  label: string
  icon?: React.ReactNode
}

interface TabsProps {
  tabs: Tab[]
  activeId: string
  onChange: (id: string) => void
  className?: string
}

export function Tabs({ tabs, activeId, onChange, className }: TabsProps) {
  return (
    <div className={cn("flex gap-1 p-1 rounded-sm bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))]", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
            activeId === tab.id
              ? "bg-[hsl(var(--card))] text-[hsl(var(--primary))] shadow-[0_0_8px_hsl(var(--primary)/0.15)] border border-[hsl(var(--primary))]/20"
              : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]",
          )}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  )
}
