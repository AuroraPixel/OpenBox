// The plan the agent drafted, before anything is built from it.
//
// A plan is prose the user is being asked to approve, so it renders as prose
// — markdown, like every other answer — rather than as the raw source. And it
// is editable in place: the whole point of the pause is that the user gets to
// change their mind, and making them reject and re-prompt to fix one line is
// a worse loop than letting them fix the line.
//
// Saving writes the file the build agent reads *and* the part this card shows,
// so what was approved and what gets built cannot drift apart.
import { lazy, Suspense, useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, ChevronDown, Pencil, X } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import type { PlanPart } from "@/shared/types/api"
import { usePlanDecision, useSavePlan } from "../api/plan"

const Markdown = lazy(() => import("./Markdown"))

/** Plan-mode proposal: the draft, editable, with accept/reject when ready. */
export function PlanPartCard({ part, sessionId }: { part: PlanPart; sessionId: string }) {
  const { t } = useTranslation("chat")
  const { accept, reject } = usePlanDecision(sessionId)
  const save = useSavePlan(sessionId)

  const [open, setOpen] = useState(true)
  const [draft, setDraft] = useState<string | null>(null)
  const editing = draft !== null

  const ready = part.status === "ready"
  const settled = part.status === "accepted" || part.status === "rejected"
  const busy = accept.isPending || reject.isPending || save.isPending

  function saveDraft() {
    if (draft === null) return
    const next = draft
    save.mutate(next, { onSuccess: () => setDraft(null) })
  }

  return (
    <div className="border-hair bg-card flex w-full max-w-165 flex-col gap-3 rounded-xl border p-5">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="group flex min-w-0 flex-1 items-center gap-2.5 text-start"
        >
          <span className="text-lg font-medium">{t("plan.review.title")}</span>
          <span className="text-n600 truncate font-mono text-xs">{part.path}</span>
          <ChevronDown
            className={cn(
              "text-n500 group-hover:text-ink size-3.5 shrink-0 transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </button>
        {/* Editing a plan that has already been accepted or rejected would
            change a record of what was decided, not a proposal. */}
        {open && !settled && !editing && (
          <button
            type="button"
            onClick={() => setDraft(part.content)}
            aria-label={t("plan.review.edit")}
            className="text-n500 hover:text-ink hover:bg-n200 shrink-0 rounded p-1.5 transition-colors"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
      </div>

      <div className="fold" data-open={open}>
        <div>
          {editing ? (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={16}
              aria-label={t("plan.review.edit")}
              className="scr border-hair bg-bg text-ink focus:border-accent max-h-100 w-full resize-y rounded-lg border p-3 font-mono text-sm leading-relaxed outline-none"
            />
          ) : (
            <div className="scr text-ink max-h-100 overflow-auto text-md leading-relaxed">
              <Suspense fallback={<p className="whitespace-pre-wrap">{part.content}</p>}>
                <Markdown text={part.content} />
              </Suspense>
            </div>
          )}

          <div className="mt-3 flex flex-wrap gap-2.5">
            {editing ? (
              <>
                <button
                  type="button"
                  onClick={saveDraft}
                  disabled={busy}
                  className="bg-ink text-bg flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm disabled:opacity-60"
                >
                  <Check className="size-3.5" />
                  {t("plan.review.save")}
                </button>
                <button
                  type="button"
                  onClick={() => setDraft(null)}
                  disabled={busy}
                  className="border-hair text-ink hover:bg-hairsoft rounded-full border px-4 py-1.5 text-sm"
                >
                  {t("plan.review.cancel")}
                </button>
              </>
            ) : ready ? (
              <>
                <button
                  type="button"
                  onClick={() => accept.mutate()}
                  disabled={busy}
                  className="bg-ink text-bg rounded-full px-4 py-1.5 text-sm disabled:opacity-60"
                >
                  {t("plan.review.accept")}
                </button>
                <button
                  type="button"
                  onClick={() => reject.mutate()}
                  disabled={busy}
                  className="border-hair text-ink hover:bg-hairsoft flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm disabled:opacity-60"
                >
                  <X className="size-3.5" />
                  {t("plan.review.reject")}
                </button>
              </>
            ) : settled ? (
              <span className="text-n600 text-sm">
                {t(part.status === "accepted" ? "plan.review.accepted" : "plan.review.rejected")}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
