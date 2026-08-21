import { useTranslation } from "react-i18next"
import { Spinner } from "@/shared/ui/Spinner"
import { formatCost, formatTokens } from "@/shared/lib/format"
import type { Session } from "@/shared/types/api"
import { useUsageSessions } from "@/features/settings/api/settings"
import { RowCard, Row } from "./SettingsRow"

function totalOf(s: Session): number {
  return s.token_usage?.total ?? 0
}

export function UsagePage() {
  const { t } = useTranslation("settings")
  const { data, isLoading } = useUsageSessions()

  if (isLoading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner className="size-5" />
      </div>
    )
  }

  const sessions = data ?? []
  const used = sessions.filter((s) => totalOf(s) > 0).sort((a, b) => totalOf(b) - totalOf(a))
  const totalTokens = used.reduce((a, s) => a + totalOf(s), 0)
  const totalCost = used.reduce((a, s) => a + (s.token_usage?.cost ?? 0), 0)
  const active = [...sessions].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))[0]
  const ctx = active?.token_usage?.context ?? 0
  const limit = active?.token_usage?.limit ?? 0
  const pct = limit > 0 ? Math.min(100, (ctx / limit) * 100) : 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-xl border border-hair bg-card px-5 py-4.5">
        <div className="flex items-baseline gap-2.5">
          <span className="text-4xl">{formatTokens(totalTokens)}</span>
          <span className="text-sm text-n600">{t("usage.totalTokens")}</span>
          <span className="ms-auto text-sm text-a700">{formatCost(totalCost)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-n200">
          <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex items-center justify-between text-xs text-n600">
          <span>{t("usage.contextUsed")}</span>
          <span className="font-mono">
            {formatTokens(ctx)} / {formatTokens(limit)}
          </span>
        </div>
        <span className="text-pretty text-xs text-n600">{t("usage.note")}</span>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-xs text-n600">{t("usage.perSession")}</span>
        {used.length === 0 ? (
          <div className="rounded-xl border border-hair bg-card px-5 py-8 text-center text-sm text-n600">
            {t("usage.empty")}
          </div>
        ) : (
          <RowCard>
            {used.map((s) => (
              <Row
                key={s.id}
                label={s.title || s.id}
                right={
                  <div className="flex flex-none items-center gap-3 text-xs">
                    <span className="font-mono text-n600">{formatTokens(totalOf(s))}</span>
                    <span className="text-a700">{formatCost(s.token_usage?.cost ?? 0)}</span>
                  </div>
                }
              />
            ))}
          </RowCard>
        )}
      </div>
    </div>
  )
}
