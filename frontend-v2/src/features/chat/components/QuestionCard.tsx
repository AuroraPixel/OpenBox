import { useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import type { QuestionRequest } from "@/shared/types/api"
import { useRejectQuestion, useReplyQuestion } from "../api/question"

/** Inline clarifying question: selectable option pills (or a free-text field). */
export function QuestionCard({ request }: { request: QuestionRequest }) {
  const { t } = useTranslation("chat")
  const reply = useReplyQuestion()
  const rejectM = useRejectQuestion()
  const options = request.options ?? []
  const multi = request.multi_select ?? false
  const [selected, setSelected] = useState<string[]>([])
  const [freeText, setFreeText] = useState("")

  const toggle = (val: string) =>
    setSelected((prev) =>
      multi ? (prev.includes(val) ? prev.filter((v) => v !== val) : [...prev, val]) : [val],
    )

  const answers = options.length > 0 ? selected : freeText.trim() ? [freeText.trim()] : []
  const submit = () => {
    if (answers.length > 0) reply.mutate({ requestId: request.id, answers })
  }

  return (
    <div className="border-hair bg-card flex max-w-165 flex-col gap-3 rounded-xl border p-5">
      <div className="flex flex-col gap-1">
        <span className="text-n600 text-sm">{request.header ?? t("question.title")}</span>
        <span className="text-ink text-base">{request.question}</span>
      </div>
      {options.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {options.map((o) => {
            const val = o.value ?? o.label
            const on = selected.includes(val)
            return (
              <button
                key={val}
                type="button"
                onClick={() => toggle(val)}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-sm",
                  on ? "border-accent bg-a100 text-a800" : "border-hair text-ink hover:bg-hairsoft",
                )}
              >
                {o.label}
              </button>
            )
          })}
        </div>
      ) : (
        <textarea
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          rows={2}
          className="scr border-hair bg-n100 text-md text-ink resize-none rounded-lg border px-3 py-2 outline-none"
        />
      )}
      <div className="flex gap-2.5">
        <button
          type="button"
          onClick={submit}
          disabled={reply.isPending || answers.length === 0}
          className="bg-ink text-bg rounded-full px-4 py-1.5 text-sm disabled:opacity-50"
        >
          {t("send")}
        </button>
        <button
          type="button"
          onClick={() => rejectM.mutate(request.id)}
          disabled={rejectM.isPending}
          className="border-hair text-ink hover:bg-hairsoft rounded-full border px-4 py-1.5 text-sm"
        >
          {t("question.reject")}
        </button>
      </div>
    </div>
  )
}
