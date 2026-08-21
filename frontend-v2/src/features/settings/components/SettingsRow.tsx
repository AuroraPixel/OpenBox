import type { ReactNode } from "react"

/** Rounded card that stacks setting rows with hairline separators. Note: no
 * `overflow-hidden` — a row's dropdown Menu must be able to spill past the card. */
export function RowCard({ children }: { children: ReactNode }) {
  return <div className="flex flex-col rounded-xl border border-hair bg-card">{children}</div>
}

interface RowProps {
  label: string
  hint?: ReactNode
  right?: ReactNode
}

/** One setting row: label + optional hint on the start, a control on the end. */
export function Row({ label, hint, right }: RowProps) {
  return (
    <div className="flex items-center gap-4 border-t border-hair px-5 py-3.5 first:border-t-0">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-base">{label}</span>
        {hint != null && hint !== "" && <span className="text-pretty text-xs text-n600">{hint}</span>}
      </div>
      {right}
    </div>
  )
}

/** Pill-shaped value control with a caret; opens a menu on click. */
export function ValuePill({ value, onClick }: { value: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-7.5 flex-none items-center gap-1.5 whitespace-nowrap rounded-full bg-n200 px-3 text-xs text-ink hover:bg-n300"
    >
      {value}
      <span className="text-2xs text-n600">▾</span>
    </button>
  )
}
