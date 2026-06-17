interface StepDividerProps {
  step: number
}

export function StepDivider({ step }: StepDividerProps) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <div className="flex-1 h-px" />
      <span className="text-[10px] font-mono text-[hsl(var(--primary))]/70 uppercase tracking-wider tabular-nums px-2 glow-cyan">
        Step {step}
      </span>
      <div className="flex-1 h-px" />
    </div>
  )
}
