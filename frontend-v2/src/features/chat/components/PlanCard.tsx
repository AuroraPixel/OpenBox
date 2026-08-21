import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import type { TodoItem } from "@/shared/types/api"

function PlanStep({ item }: { item: TodoItem }) {
  const running = item.status === "in_progress"
  const done = item.status === "completed"
  return (
    <div className="flex min-h-8 items-center gap-3 rounded-full px-2.5 py-1">
      <span
        className={cn(
          "text-bg box-border flex size-4.5 flex-none items-center justify-center rounded-full text-[10px]",
          done ? "bg-s600" : running ? "border-accent border-[2.5px]" : "border-n400 border-[2.5px]",
        )}
      >
        {done ? "✓" : ""}
      </span>
      <span className={cn("text-base", running ? "text-ink font-medium" : done ? "text-n700" : "text-n500")}>
        {running && item.active_form ? item.active_form : item.subject}
      </span>
    </div>
  )
}

interface Props {
  items: TodoItem[]
  onStop?: () => void
}

/** The task-plan card, driven by the session todo list (read-only). */
export function PlanCard({ items, onStop }: Props) {
  const { t } = useTranslation("chat")
  const total = items.length
  const doneCount = items.filter((i) => i.status === "completed").length
  const current = Math.min(total, doneCount + 1)
  return (
    <div className="border-hair bg-card flex max-w-165 flex-col gap-3 rounded-xl border p-5">
      <div className="flex items-center gap-2.5">
        <span className="text-lg font-medium">{t("plan.title")}</span>
        {total > 0 && <span className="text-n600 text-sm">{t("plan.stepCounter", { current, total })}</span>}
        {onStop && (
          <button type="button" onClick={onStop} className="text-a700 hover:text-accent ms-auto text-sm">
            {t("plan.stop")}
          </button>
        )}
      </div>
      <div className="flex flex-col">
        {items.map((it) => (
          <PlanStep key={it.id} item={it} />
        ))}
      </div>
    </div>
  )
}
