import { useTranslation } from "react-i18next"
import type { PlanPart } from "@/shared/types/api"
import { usePlanDecision } from "../api/plan"

/** Plan-mode proposal: shows the drafted plan and, when ready, accept/reject. */
export function PlanPartCard({ part, sessionId }: { part: PlanPart; sessionId: string }) {
  const { t } = useTranslation("chat")
  const { accept, reject } = usePlanDecision(sessionId)
  const ready = part.status === "ready"
  const busy = accept.isPending || reject.isPending
  return (
    <div className="border-hair bg-card flex max-w-165 flex-col gap-3 rounded-xl border p-5">
      <div className="flex items-center gap-2.5">
        <span className="text-lg font-medium">{t("plan.review.title")}</span>
        <span className="text-n600 font-mono text-xs">{part.path}</span>
      </div>
      <div className="scr text-md text-n800 max-h-100 overflow-auto leading-relaxed whitespace-pre-wrap">
        {part.content}
      </div>
      {ready && (
        <div className="flex gap-2.5">
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
            className="border-hair text-ink hover:bg-hairsoft rounded-full border px-4 py-1.5 text-sm"
          >
            {t("plan.review.reject")}
          </button>
        </div>
      )}
    </div>
  )
}
