interface ToolReadProps {
  input?: Record<string, unknown>
  output?: string
}

export function ToolRead({ input, output }: ToolReadProps) {
  const filePath = String(input?.file_path || input?.path || "")
  const lines = (output || "").split("\n")
  const maxLines = 15
  const truncated = lines.length > maxLines

  return (
    <div className="font-mono text-[11px]">
      {filePath && (
        <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] text-[hsl(var(--accent))] glow-amber">
          {filePath}
        </div>
      )}
      {output && (
        <div className="px-3.5 py-2.5 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto leading-relaxed bg-[hsl(var(--terminal-bg))]">
          {lines.slice(0, maxLines).map((line, i) => (
            <div key={i} className="flex">
              <span className="w-10 text-right pr-3 text-[hsl(var(--muted-foreground))]/50 select-none shrink-0 tabular-nums">{i + 1}</span>
              <span>{line}</span>
            </div>
          ))}
          {truncated && (
            <div className="text-[hsl(var(--muted-foreground))]/60 mt-1.5 pl-10 tabular-nums font-mono uppercase tracking-wider">
              ... {lines.length - maxLines} more lines
            </div>
          )}
        </div>
      )}
    </div>
  )
}
