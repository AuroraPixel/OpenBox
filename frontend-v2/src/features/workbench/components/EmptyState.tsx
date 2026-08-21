// Centered empty/placeholder state shared by the terminal / browser / files
// tabs: a title, an optional hint, and an optional primary action button.
import { Spinner } from "@/shared/ui/Spinner"

interface Action {
  label: string
  onClick: () => void
  pending?: boolean
}

interface EmptyStateProps {
  title: string
  hint?: string
  action?: Action
}

export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
      <span className="text-md font-medium text-n700">{title}</span>
      {hint && <span className="max-w-xs text-sm text-n600">{hint}</span>}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          disabled={action.pending}
          className="mt-2 inline-flex h-8 items-center gap-2 rounded-full bg-ink px-4 text-sm text-bg hover:opacity-90 disabled:opacity-60"
        >
          {action.pending && <Spinner className="size-3.5 border-bg/40 border-t-bg" />}
          {action.label}
        </button>
      )}
    </div>
  )
}
