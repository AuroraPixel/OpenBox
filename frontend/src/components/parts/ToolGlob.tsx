import { FileText } from "lucide-react"

interface ToolGlobProps {
  input?: Record<string, unknown>
  output?: string
}

export function ToolGlob({ input, output }: ToolGlobProps) {
  const pattern = String(input?.pattern || "")
  const files = (output || "").split("\n").filter(Boolean)

  return (
    <div className="font-mono text-[11px]">
      <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] text-[hsl(var(--muted-foreground))]">
        <span className="font-mono uppercase tracking-wider text-[10px]">pattern:</span> <span className="text-[hsl(var(--accent))]">&quot;{pattern}&quot;</span>
      </div>
      <div className="px-3.5 py-2.5 space-y-0.5 overflow-x-auto max-h-48 overflow-y-auto bg-[hsl(var(--terminal-bg))]">
        {files.slice(0, 30).map((file, i) => (
          <div key={i} className="flex items-center gap-2 hover:bg-[hsl(var(--surface-1))] rounded-sm px-1.5 py-0.5 cursor-pointer transition-colors">
            <FileText className="h-3 w-3 text-[hsl(var(--muted-foreground))]/60 shrink-0" />
            <span className="truncate text-[hsl(var(--accent))]">{file}</span>
          </div>
        ))}
        {files.length > 30 && (
          <div className="text-[hsl(var(--muted-foreground))]/60 tabular-nums font-mono uppercase tracking-wider">... {files.length - 30} more files</div>
        )}
        <div className="text-[hsl(var(--muted-foreground))]/60 mt-1.5 pt-1.5 border-t border-[hsl(var(--border))]/30 tabular-nums font-mono uppercase tracking-wider">
          {files.length} files
        </div>
      </div>
    </div>
  )
}
