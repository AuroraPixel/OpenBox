// Shared building blocks for a tool's detail column, ported 1:1 from
// DEEIX-Chat's message-tool-trace primitives (ToolMiniLabel / ToolPre /
// ToolSourceLinks / ToolDetailText) and translated onto bossip tokens.
import { useLayoutEffect, useRef, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { dedupeUrls, safeHostname } from "../../lib/tool-parse"

const COLLAPSED_LINES = 8
const LINE_HEIGHT_REM = 1.25

/** Faint section caption above a request/response block. */
export function ToolMiniLabel({ children }: { children: ReactNode }) {
  return <div className="text-2xs text-n600/58 mb-1 leading-4 font-medium">{children}</div>
}

/** Monospace code/output box; red-toned on failure, null when empty. */
export function ToolPre({ children, failed }: { children: string; failed?: boolean }) {
  if (!children.trim()) return null
  return (
    <pre
      className={cn(
        "border-hair/60 bg-n200/25 text-n700 max-h-56 overflow-auto rounded-md border px-2.5 py-2 font-mono text-2xs leading-5 break-words whitespace-pre-wrap",
        failed && "border-danger/25 bg-dangersoft text-danger",
      )}
    >
      {children}
    </pre>
  )
}

/** Row of domain pills linking to sources, deduped and capped at eight. */
export function ToolSourceLinks({ urls }: { urls: string[] }) {
  const { t } = useTranslation("chat")
  const unique = dedupeUrls(urls, 8)
  if (unique.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {unique.map((url, index) => (
        <a
          key={`${url}-${index}`}
          href={url}
          target="_blank"
          rel="noreferrer"
          title={url}
          className="border-hair/60 bg-bg/55 text-n700 hover:border-hair hover:text-ink max-w-55 truncate rounded-full border px-2 py-0.5 text-2xs font-medium transition-colors"
        >
          {safeHostname(url) || t("toolDetail.sourceFallback", { index: index + 1 })}
        </a>
      ))}
    </div>
  )
}

/** Long text clamped to eight lines behind a fade, with an expand toggle. */
export function ToolDetailText({ failed, children }: { failed?: boolean; children: ReactNode }) {
  const { t } = useTranslation("chat")
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [height, setHeight] = useState(0)
  const [clamp, setClamp] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => {
      setHeight(el.scrollHeight)
      setClamp(el.scrollHeight > COLLAPSED_LINES * LINE_HEIGHT_REM * 16)
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [children])

  const maxHeight = clamp ? (open ? `${height}px` : `${COLLAPSED_LINES * LINE_HEIGHT_REM}rem`) : undefined

  return (
    <>
      <div className="relative">
        <div
          ref={ref}
          className={cn(
            "overflow-hidden font-mono break-words whitespace-pre-wrap transition-[max-height] duration-200 ease-out",
            failed ? "text-danger" : "text-n700",
          )}
          style={maxHeight ? { maxHeight } : undefined}
        >
          {children}
        </div>
        {clamp && !open && (
          <div className="from-bg/0 via-bg/88 to-bg pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-b" />
        )}
      </div>
      {clamp && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="text-a700 hover:text-accent mt-0.5 text-xs"
        >
          {open ? t("toolDetail.collapse") : t("toolDetail.expand")}
        </button>
      )}
    </>
  )
}
