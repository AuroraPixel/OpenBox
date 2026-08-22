// The agent's clarifying questions, asked just above the composer.
//
// This is a turn-taking moment, not a message: the run is blocked until the
// user answers, and the answer is the next thing they will "say". Putting it
// in the scroll area meant it could sit off-screen while the run waited, and
// it read as history rather than as something wanting a reply. It rises from
// the composer instead, where the user's attention already is.
//
// Once answered it disappears — the exchange lives on in the conversation as
// the question tool's own row, so nothing is lost by dismissing it here.
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Check } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import type { QuestionItem, QuestionRequest } from "@/shared/types/api"
import { useRejectQuestion, useReplyQuestion } from "../api/question"

/** Chosen labels per question, in the order asked. */
type Draft = string[][]

function isAnswered(draft: Draft, index: number): boolean {
  return (draft[index]?.length ?? 0) > 0
}

interface OneProps {
  item: QuestionItem
  index: number
  total: number
  picked: string[]
  onPick: (labels: string[]) => void
}

function OneQuestion({ item, index, total, picked, onPick }: OneProps) {
  const { t } = useTranslation("chat")
  const [custom, setCustom] = useState("")
  const options = item.options ?? []
  const multiple = item.multiple ?? false
  // Absent means allowed — only an explicit false closes it.
  const allowCustom = item.custom !== false

  const toggle = (label: string) => {
    if (!multiple) return onPick([label])
    onPick(picked.includes(label) ? picked.filter((v) => v !== label) : [...picked, label])
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-0.5">
        <span className="text-n600 flex items-center gap-1.5 text-xs">
          {item.header || t("question.title")}
          {total > 1 && (
            <span className="text-n500">
              {index + 1}/{total}
            </span>
          )}
        </span>
        <span className="text-ink text-base">{item.question}</span>
      </div>

      {options.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {options.map((o) => {
            const on = picked.includes(o.label)
            return (
              <button
                key={o.label}
                type="button"
                onClick={() => toggle(o.label)}
                title={o.description}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                  on ? "border-accent bg-a100 text-a800" : "border-hair text-ink hover:bg-hairsoft",
                )}
              >
                {on && <Check className="size-3" strokeWidth={3} />}
                {o.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Offered unless the asker closed it. The agent is told not to add a
          catch-all option because this is here, so its questions always keep
          it; only the system's own — plan mode's Yes/No — turn it off, where
          a text box would invite an answer nothing reads. */}
      {allowCustom && (
        <input
          value={custom}
          onChange={(e) => {
            setCustom(e.target.value)
            const text = e.target.value.trim()
            onPick(text ? [text] : [])
          }}
          placeholder={options.length > 0 ? t("question.other") : t("question.answer")}
          aria-label={item.question}
          className="border-hair bg-bg text-ink placeholder:text-n500 focus:border-accent w-full rounded-lg border px-3 py-1.5 text-sm outline-none"
        />
      )}
    </div>
  )
}

export function QuestionDock({ request }: { request: QuestionRequest }) {
  const { t } = useTranslation("chat")
  const reply = useReplyQuestion()
  const reject = useRejectQuestion()
  const questions = request.questions ?? []
  const [draft, setDraft] = useState<Draft>(() => questions.map(() => []))

  const complete = questions.every((_, i) => isAnswered(draft, i))
  const busy = reply.isPending || reject.isPending

  if (questions.length === 0) return null

  return (
    <div className="border-hair bg-card mx-auto mb-2 w-full max-w-190 rounded-xl border p-4 shadow-sm">
      <div className="flex flex-col gap-4">
        {questions.map((item, i) => (
          <OneQuestion
            key={`${request.id}:${i}`}
            item={item}
            index={i}
            total={questions.length}
            picked={draft[i] ?? []}
            onPick={(labels) => setDraft((prev) => prev.map((cur, j) => (j === i ? labels : cur)))}
          />
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2.5">
        <button
          type="button"
          onClick={() => reply.mutate({ requestId: request.id, answers: draft })}
          disabled={!complete || busy}
          className="bg-ink text-bg rounded-full px-4 py-1.5 text-sm disabled:opacity-40"
        >
          {t("question.submit")}
        </button>
        <button
          type="button"
          onClick={() => reject.mutate(request.id)}
          disabled={busy}
          className="border-hair text-ink hover:bg-hairsoft rounded-full border px-4 py-1.5 text-sm disabled:opacity-60"
        >
          {t("question.skip")}
        </button>
        {!complete && (
          <span className="text-n600 text-xs">{t("question.needAll", { count: questions.length })}</span>
        )}
      </div>
    </div>
  )
}
