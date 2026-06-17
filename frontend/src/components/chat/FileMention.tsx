import { FileText } from "lucide-react"

interface FileMentionProps {
  suggestions: string[]
  onSelect: (path: string) => void
}

export function FileMention({ suggestions, onSelect }: FileMentionProps) {
  if (suggestions.length === 0) return null

  return (
    <div className="absolute bottom-full left-0 mb-2 w-80 rounded-sm border border-[hsl(var(--primary))]/20 bg-[hsl(var(--card))] shadow-[0_0_16px_hsl(var(--primary)/0.1)] py-1.5 z-10 max-h-48 overflow-y-auto animate-fade-in">
      {suggestions.map((path) => (
        <button
          key={path}
          onClick={() => onSelect(path)}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-sm hover:bg-[hsl(var(--primary))]/10 transition-colors cursor-pointer"
        >
          <FileText className="h-3.5 w-3.5 text-[hsl(var(--accent))]" />
          <span className="font-mono text-xs truncate text-[hsl(var(--foreground))]">{path}</span>
        </button>
      ))}
    </div>
  )
}
