interface ToolEditProps {
  input?: Record<string, unknown>
  output?: string
}

export function ToolEdit({ input, output }: ToolEditProps) {
  const filePath = String(input?.file_path || input?.path || "")
  const oldStr = String(input?.old_string || "")
  const newStr = String(input?.new_string || "")

  return (
    <div className="font-mono text-[11px]">
      {filePath && (
        <div className="px-3.5 py-2 bg-[hsl(var(--surface-1))] text-[hsl(var(--accent))] glow-amber">
          {filePath}
        </div>
      )}
      <div className="px-3.5 py-2.5 space-y-0.5 overflow-x-auto max-h-64 overflow-y-auto bg-[hsl(var(--terminal-bg))]">
        {oldStr && oldStr.split("\n").map((line, i) => (
          <div key={`old-${i}`} className="flex bg-[hsl(var(--destructive))]/8 text-[hsl(var(--destructive))] rounded-sm px-1.5 py-px">
            <span className="text-[hsl(var(--destructive))]/50 mr-2.5 select-none">-</span>
            <span>{line}</span>
          </div>
        ))}
        {newStr && newStr.split("\n").map((line, i) => (
          <div key={`new-${i}`} className="flex bg-[hsl(var(--success))]/8 text-[hsl(var(--success))] rounded-sm px-1.5 py-px">
            <span className="text-[hsl(var(--success))]/50 mr-2.5 select-none">+</span>
            <span>{line}</span>
          </div>
        ))}
        {output && !oldStr && !newStr && (
          <pre className="whitespace-pre-wrap leading-relaxed">{output}</pre>
        )}
      </div>
    </div>
  )
}
