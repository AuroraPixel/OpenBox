// How full the context window is, as a ring beside the model picker.
//
// A ring rather than a token count: mid-conversation the useful question is
// "how close am I to compaction", which a fraction answers at a glance while
// "14.5k tokens" only answers if you happen to remember the model's window —
// and that window changes the moment the picker next to it changes. The exact
// numbers stay one hover away.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { formatTokens } from "@/shared/lib/format"
import { Tooltip } from "@/shared/ui/Tooltip"

/** Geometry of the 16px ring: r=6 with a 2px stroke leaves a hairline of
 *  padding inside the box, so it sits level with the adjacent text. */
const R = 6
const CIRCUMFERENCE = 2 * Math.PI * R

/** Where the ring stops being informational and starts being a warning. */
const WARN_AT = 0.7
const CRITICAL_AT = 0.9

interface Props {
  /** Tokens the next request will carry: history + system prompt + tools. */
  used: number
  /** The selected model's context window. */
  limit: number
}

export function ContextRing({ used, limit }: Props) {
  const { t } = useTranslation("chat")
  // Nothing honest to draw until the backend has told us the window size.
  if (limit <= 0) return null

  const ratio = Math.min(1, Math.max(0, used / limit))
  // Never round a non-empty context down to a bare ring — 0% next to a visible
  // arc reads as a bug. Same at the top: only a genuinely full window says 100%.
  const pct = used > 0 ? Math.max(1, Math.round(ratio * 100)) : 0
  const level = ratio >= CRITICAL_AT ? "critical" : ratio >= WARN_AT ? "warn" : "calm"
  const stroke =
    level === "critical" ? "stroke-danger" : level === "warn" ? "stroke-accent" : "stroke-n700"
  const remaining = Math.max(0, limit - used)

  const detail = (
    <span className="flex flex-col gap-0.5">
      <span className="font-medium">{t("context.title")}</span>
      <span className="text-n700">
        {t("context.used", {
          used: formatTokens(used),
          limit: formatTokens(limit),
          pct,
        })}
      </span>
      <span className="text-n600">{t("context.left", { tokens: formatTokens(remaining) })}</span>
      {level !== "calm" && (
        <span className={cn(level === "critical" ? "text-danger" : "text-accent")}>
          {t("context.compactSoon")}
        </span>
      )}
    </span>
  )

  return (
    <Tooltip label={detail}>
      <span
        className="flex size-8 flex-none items-center justify-center"
        role="img"
        aria-label={t("context.aria", { pct })}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
          <circle className="stroke-n400/70" cx="8" cy="8" r={R} fill="none" strokeWidth="2" />
          <circle
            className={cn(stroke, "transition-[stroke-dashoffset,stroke] duration-300")}
            cx="8"
            cy="8"
            r={R}
            fill="none"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - ratio)}
            // Start the arc at 12 o'clock and fill clockwise, the way every
            // other progress ring the user has met behaves.
            transform="rotate(-90 8 8)"
          />
        </svg>
      </span>
    </Tooltip>
  )
}
