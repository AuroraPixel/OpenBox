// Process trace, ported from DEEIX-Chat's MessageProcessTrace: 处理完成 over
// "准备 N tokens 上下文". Body lists the turn's real stages — context size and
// wall-clock — no invented data.
import { useTranslation } from "react-i18next"
import { formatDuration, formatNumber } from "@/shared/lib/format"
import { TraceShell } from "./TraceShell"

interface Props {
  contextTokens: number
  durationSec: number
  streaming: boolean
  autoCollapseReady: boolean
}

function Stage({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs grid grid-cols-[8rem_minmax(0,1fr)] gap-x-5 leading-5 max-sm:grid-cols-1 max-sm:gap-x-0">
      <span className="text-n700 truncate font-medium">{label}</span>
      <span className="text-n600 min-w-0 truncate">{value}</span>
    </div>
  )
}

export function ProcessTrace({ contextTokens, durationSec, streaming, autoCollapseReady }: Props) {
  const { t } = useTranslation("chat")
  if (contextTokens <= 0 && durationSec <= 0) return null
  return (
    <TraceShell
      title={streaming ? t("trace.process.titleActive") : t("trace.process.titleDone")}
      subtitle={
        contextTokens > 0
          ? t("trace.process.prepared", { tokens: formatNumber(contextTokens) })
          : undefined
      }
      streaming={streaming}
      autoCollapseReady={autoCollapseReady}
    >
      <div className="space-y-0.5">
        {contextTokens > 0 && (
          <Stage
            label={t("trace.process.stageContext")}
            value={t("trace.process.contextTokens", { tokens: formatNumber(contextTokens) })}
          />
        )}
        {durationSec > 0 && (
          <Stage
            label={t("trace.process.stageResult")}
            value={t("trace.process.duration", { duration: formatDuration(durationSec) })}
          />
        )}
      </div>
    </TraceShell>
  )
}
