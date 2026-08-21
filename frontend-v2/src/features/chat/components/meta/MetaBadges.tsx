// The data badges that sit above an assistant turn's action row, plus the
// shared timestamp label. All colours/sizes are token-driven (design appendix D).
import type { ReactNode } from "react"
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  CircleDollarSign,
  ClockArrowUp,
  ClockCheck,
  Cpu,
  Database,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { useLiveElapsed } from "@/shared/hooks/useLiveElapsed"
import { cn } from "@/shared/lib/cn"
import { formatCost, formatDuration, formatNumber } from "@/shared/lib/format"
import { Tooltip } from "@/shared/ui/Tooltip"
import type { TokenUsage } from "@/shared/types/api"
import { useSessionQuery } from "../../api/message-actions"

const BADGE =
  "ms-0.5 inline-flex items-center gap-1.5 rounded bg-n200/40 px-1.5 py-0.5 font-mono text-2xs leading-3.5 text-n600/70 select-none whitespace-nowrap"

/** Cpu + model name; the full name lives in the tooltip. */
export function ModelBadge({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation("chat")
  const { data } = useSessionQuery(sessionId)
  const model = data?.model?.trim()
  if (!model) return null
  return (
    <Tooltip label={model}>
      <span aria-label={t("meta.model")} className={cn(BADGE, "max-w-48")}>
        <Cpu className="size-3 shrink-0" strokeWidth={1.4} />
        <span className="truncate">{model}</span>
      </span>
    </Tooltip>
  )
}

function TokenMetric({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return (
    <Tooltip label={label}>
      <span className="inline-flex items-center gap-0.5" aria-label={label}>
        {icon}
        {value}
      </span>
    </Tooltip>
  )
}

/** Input / output / cache token counts, plus cost when the backend priced it. */
export function TokenBadge({ tokens }: { tokens: TokenUsage }) {
  const { t } = useTranslation("chat")
  const input = tokens.input ?? 0
  const output = tokens.output ?? 0
  const cache = tokens.cache ?? 0
  const cost = tokens.cost ?? 0
  if (input <= 0 && output <= 0 && cache <= 0) return null
  return (
    <span className={BADGE}>
      {input > 0 && (
        <TokenMetric
          label={t("meta.inputTokens")}
          value={formatNumber(input)}
          icon={<ArrowUpFromLine className="size-3" strokeWidth={1.4} />}
        />
      )}
      {output > 0 && (
        <TokenMetric
          label={t("meta.outputTokens")}
          value={formatNumber(output)}
          icon={<ArrowDownToLine className="size-3" strokeWidth={1.4} />}
        />
      )}
      {cache > 0 && (
        <TokenMetric
          label={t("meta.cacheTokens")}
          value={formatNumber(cache)}
          icon={<Database className="size-3" strokeWidth={1.4} />}
        />
      )}
      {cost > 0 && (
        <TokenMetric
          label={t("meta.cost")}
          value={formatCost(cost)}
          icon={<CircleDollarSign className="size-3" strokeWidth={1.4} />}
        />
      )}
    </span>
  )
}

/** Live-ticking elapsed time while streaming, total wall-clock once finished. */
export function LatencyBadge({
  createdAt,
  streaming,
  durationSec,
}: {
  createdAt: string
  streaming: boolean
  durationSec: number
}) {
  const { t } = useTranslation("chat")
  const liveMs = useLiveElapsed(createdAt, streaming)
  const seconds = streaming ? liveMs / 1000 : durationSec
  if (seconds <= 0) return null
  const desc = streaming ? t("meta.generationDuration") : t("meta.totalDuration")
  return (
    <Tooltip label={desc}>
      <span aria-label={desc} className={BADGE}>
        {streaming ? (
          <ClockArrowUp className="size-3" strokeWidth={1.4} />
        ) : (
          <ClockCheck className="size-3" strokeWidth={1.4} />
        )}
        {formatDuration(seconds)}
      </span>
    </Tooltip>
  )
}

interface TimestampParts {
  label: string
  title: string
}

/** Today → "Today HH:MM", otherwise the full localized date + time. */
function useTimestamp(iso: string): TimestampParts | null {
  const { t, i18n } = useTranslation("common")
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const time = new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit" }).format(date)
  const day = new Intl.DateTimeFormat(i18n.language, { year: "numeric", month: "short", day: "numeric" }).format(date)
  const title = t("time.fullDateTime", { date: day, time })
  return { label: isToday ? t("time.todayTime", { time }) : title, title }
}

export function MessageTimestamp({ iso }: { iso: string }) {
  const stamp = useTimestamp(iso)
  if (!stamp) return null
  return (
    <span className="text-n600 inline-flex h-6 items-center tabular-nums" title={stamp.title}>
      {stamp.label}
    </span>
  )
}
