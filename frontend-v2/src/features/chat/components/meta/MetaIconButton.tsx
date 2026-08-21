// A 24px icon button for the message meta strip, wrapped in a tooltip.
import type { ReactNode } from "react"
import { Tooltip } from "@/shared/ui/Tooltip"
import { cn } from "@/shared/lib/cn"

interface Props {
  label: string
  active?: boolean
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
}

export function MetaIconButton({ label, active, disabled, onClick, children }: Props) {
  return (
    <Tooltip label={label} side="top">
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        className={cn(
          "text-n600 hover:text-ink inline-flex size-6 items-center justify-center rounded-md transition-colors disabled:opacity-40",
          active && "text-ink",
        )}
      >
        {children}
      </button>
    </Tooltip>
  )
}
