interface ToolGrepProps {
  input?: Record<string, unknown>
  output?: string
}

export function ToolGrep({ input, output }: ToolGrepProps) {
  const pattern = String(input?.pattern || "")
  const path = String(input?.path || "")
  const lines = (output || "").split("\n").filter(Boolean)

  return (
    <div className="font-mono text-[11px]">
      <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] text-[hsl(var(--muted-foreground))]">
        <span className="font-mono uppercase tracking-wider text-[10px]">pattern:</span> <span className="text-[hsl(var(--primary))]">&quot;{pattern}&quot;</span> {path && <><span className="font-mono uppercase tracking-wider text-[10px]">path:</span> <span className="text-[hsl(var(--accent))]">{path}</span></>}
      </div>
      <div className="px-3.5 py-2.5 space-y-0.5 overflow-x-auto max-h-48 overflow-y-auto bg-[hsl(var(--terminal-bg))]">
        {lines.slice(0, 30).map((line, i) => (
          <div key={i} className="text-[hsl(var(--foreground))] hover:bg-[hsl(var(--surface-1))] rounded-sm px-1.5 py-0.5 cursor-pointer transition-colors">
            {line}
          </div>
        ))}
        {lines.length > 30 && (
          <div className="text-[hsl(var(--muted-foreground))]/60 tabular-nums font-mono uppercase tracking-wider">... {lines.length - 30} more matches</div>
        )}
        {lines.length > 0 && (
          <div className="text-[hsl(var(--muted-foreground))]/60 mt-1.5 pt-1.5 border-t border-[hsl(var(--border))]/30 tabular-nums font-mono uppercase tracking-wider">
            {lines.length} matches
          </div>
        )}
      </div>
    </div>
  )
}
