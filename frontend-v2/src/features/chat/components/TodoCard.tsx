// The task card: the model's todo list, with each task's own calls folded
// underneath it.
//
// This replaces the flat tool chain for turns that kept a list. The chain
// shows what happened; the card shows what it was *for* — which is the whole
// point of the list existing. Calls that fell outside any task still render
// as a chain, above and below the card.
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, ChevronDown, Plus, X } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import type { TodoItem } from "@/shared/types/api"
import { useAddTodoItem, useRemoveTodoItem } from "../api/todo"
import { progressPercent, taskProgress } from "../lib/todo-progress"
import type { TodoTask, TodoView } from "../lib/turn-view"
import { TaskToolRows } from "./TaskToolRows"

/** How often the running task's bar is recomputed. The value itself is a
 *  pure function of `started_at`, so this only decides how smooth it looks —
 *  a reload recomputes it from scratch and lands in the same place. */
const TICK_MS = 1000

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(id)
  }, [active])
  return now
}

function StatusMark({ item }: { item: TodoItem }) {
  const done = item.status === "completed"
  const running = item.status === "in_progress"
  const cancelled = item.status === "cancelled"
  return (
    <span
      className={cn(
        "box-border flex size-4.5 flex-none items-center justify-center rounded-full transition-colors",
        done && "bg-s600 text-bg",
        running && "border-accent border-[2.5px]",
        !done && !running && "border-n400 border-[2.5px]",
        cancelled && "opacity-60",
      )}
    >
      {done ? <Check className="size-3" strokeWidth={3} /> : null}
    </span>
  )
}

interface RowProps {
  task: TodoTask
  now: number
  editable: boolean
  onAdd: (afterId: string) => void
  onRemove: (id: string) => void
}

function TaskRow({ task, now, editable, onAdd, onRemove }: RowProps) {
  const { t } = useTranslation("chat")
  const { item, tools } = task
  const running = item.status === "in_progress"
  const done = item.status === "completed"
  const cancelled = item.status === "cancelled"

  // A finished task folds its work away; the running one stays open so the
  // calls stream where they happen. Latched after that, so the fold does not
  // snap shut under the user the moment the task completes.
  const [open, setOpen] = useState(running)
  const [wasRunning, setWasRunning] = useState(running)
  if (wasRunning !== running) {
    setWasRunning(running)
    if (running) setOpen(true)
  }

  const done_ = tools.filter((p) => p.status !== "running" && p.status !== "pending").length
  const value = running ? taskProgress({ startedAt: item.started_at, steps: done_, now }) : 0
  const percent = done ? 100 : progressPercent(value)

  return (
    <li className="group/task">
      <div className="flex min-h-8 items-center gap-3 rounded-lg px-2.5 py-1">
        <StatusMark item={item} />
        <button
          type="button"
          onClick={() => tools.length > 0 && setOpen((o) => !o)}
          disabled={tools.length === 0}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-1.5 text-start",
            tools.length > 0 && "cursor-pointer",
          )}
        >
          <span
            className={cn(
              "truncate text-base transition-colors",
              running && "text-ink font-medium",
              done && "text-n700",
              !running && !done && "text-n500",
              cancelled && "text-n500 line-through",
            )}
          >
            {running && item.active_form ? item.active_form : item.subject}
          </span>
          {tools.length > 0 && (
            <ChevronDown
              className={cn(
                "text-n500 size-3.5 shrink-0 transition-transform duration-200",
                open && "rotate-180",
              )}
            />
          )}
        </button>

        {running && <span className="text-n600 shrink-0 text-sm tabular-nums">{percent}%</span>}

        {editable && !running && !done && (
          <span className="ms-auto flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover/task:opacity-100 focus-within:opacity-100">
            <button
              type="button"
              onClick={() => onAdd(item.id)}
              aria-label={t("todo.addAfter")}
              className="text-n500 hover:text-ink hover:bg-n200 rounded p-1 transition-colors"
            >
              <Plus className="size-3.5" />
            </button>
            {!cancelled && (
              <button
                type="button"
                onClick={() => onRemove(item.id)}
                aria-label={t("todo.remove")}
                className="text-n500 hover:text-danger hover:bg-n200 rounded p-1 transition-colors"
              >
                <X className="size-3.5" />
              </button>
            )}
          </span>
        )}
      </div>

      {running && (
        <div className="bg-n300 mx-2.5 mt-0.5 mb-1.5 h-1 overflow-hidden rounded-full">
          <div
            className="bg-accent h-full rounded-full transition-[width] duration-1000 ease-linear"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}

      {tools.length > 0 && (
        <div className="fold" data-open={open}>
          <div>
            <div className="border-hair ms-4.5 border-s ps-4 pb-1">
              <TaskToolRows tools={tools} />
            </div>
          </div>
        </div>
      )}
    </li>
  )
}

interface Props {
  todo: TodoView
  sessionId: string
  /** The turn is live — the card offers to stop it and keeps its bar moving. */
  streaming: boolean
  onStop?: () => void
}

export function TodoCard({ todo, sessionId, streaming, onStop }: Props) {
  const { t } = useTranslation("chat")
  const now = useNow(streaming && !todo.allDone)
  const add = useAddTodoItem(sessionId)
  const remove = useRemoveTodoItem(sessionId)
  const [adding, setAdding] = useState<string | null>(null)
  const [draft, setDraft] = useState("")

  // Once every task is done the card is a record, not a control: it folds to
  // its heading and stops offering edits, because there is no run left for an
  // added task to join.
  const [open, setOpen] = useState(!todo.allDone)
  const [wasDone, setWasDone] = useState(todo.allDone)
  if (wasDone !== todo.allDone) {
    setWasDone(todo.allDone)
    setOpen(!todo.allDone)
  }

  const editable = !todo.allDone
  const heading = todo.activeForm ?? t(streaming ? "todo.working" : "todo.title")

  function submit() {
    const subject = draft.trim()
    if (!subject) return setAdding(null)
    add.mutate({ subject, afterId: adding === "end" ? undefined : adding ?? undefined })
    setDraft("")
    setAdding(null)
  }

  return (
    <div className="border-hair bg-card mb-2 flex w-full max-w-165 flex-col rounded-xl border p-4">
      <div className="flex items-center gap-2.5 px-1">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="group flex min-w-0 flex-1 items-center gap-2.5 text-start"
        >
          <span
            className={cn(
              "truncate text-base font-medium",
              streaming && !todo.allDone ? "text-shimmer" : "text-ink",
            )}
          >
            {heading}
          </span>
          {todo.total > 0 && (
            <span className="text-n600 shrink-0 text-sm">
              {todo.allDone
                ? t("todo.allDone", { total: todo.total })
                : t("plan.stepCounter", { current: Math.max(1, todo.current), total: todo.total })}
            </span>
          )}
          <ChevronDown
            className={cn(
              "text-n500 group-hover:text-ink size-3.5 shrink-0 transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </button>
        {streaming && onStop && (
          <button
            type="button"
            onClick={onStop}
            className="text-a700 hover:text-accent shrink-0 text-sm"
          >
            {t("plan.stop")}
          </button>
        )}
      </div>

      <div className="fold" data-open={open}>
        <div>
          <ul className="mt-2 flex flex-col">
            {todo.tasks.map((task) => (
              <TaskRow
                key={task.item.id}
                task={task}
                now={now}
                editable={editable}
                onAdd={(id) => {
                  setAdding(id)
                  setDraft("")
                }}
                onRemove={(id) => remove.mutate(id)}
              />
            ))}
          </ul>

          {editable && (
            <div className="mt-1 px-2.5">
              {adding !== null ? (
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={submit}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submit()
                    if (e.key === "Escape") setAdding(null)
                  }}
                  placeholder={t("todo.addPlaceholder")}
                  aria-label={t("todo.addPlaceholder")}
                  className="border-hair bg-bg text-ink placeholder:text-n500 w-full rounded-lg border px-2.5 py-1.5 text-base outline-none focus:border-accent"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setAdding("end")
                    setDraft("")
                  }}
                  className="text-a700 hover:text-accent text-sm"
                >
                  {t("plan.addStep")}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
