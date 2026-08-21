// Thinking trace, ported from DEEIX-Chat's MessageUpstreamThink: title flips
// between 正在思考 / 思考完成 with a fixed explanatory subtitle, body renders
// the reasoning as muted markdown.
import { lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"
import { TraceShell } from "./TraceShell"

const Markdown = lazy(() => import("./Markdown"))

interface Props {
  text: string
  streaming: boolean
  autoCollapseReady: boolean
}

export function ThinkingTrace({ text, streaming, autoCollapseReady }: Props) {
  const { t } = useTranslation("chat")
  if (!text.trim()) return null
  return (
    <TraceShell
      title={streaming ? t("trace.think.titleActive") : t("trace.think.titleDone")}
      subtitle={streaming ? t("trace.think.subtitleActive") : t("trace.think.subtitleDone")}
      streaming={streaming}
      autoCollapseReady={autoCollapseReady}
    >
      <div className="max-w-165">
        <Suspense fallback={<span className="text-n700 text-md whitespace-pre-wrap">{text}</span>}>
          <Markdown text={text} streaming={streaming} variant="thinking" />
        </Suspense>
      </div>
    </TraceShell>
  )
}
