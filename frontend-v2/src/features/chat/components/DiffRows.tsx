// Shared unified-diff renderer: a coloured stripe, a line-number gutter and a
// +/− marker per changed line, with untouched stretches collapsed into
// "N unmodified lines" bars. Used by both the turn's change card and the file
// tools inside the tool chain, so an edit looks the same wherever it appears.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import type { PreviewRow } from "../lib/diff-preview"

// Rows are spans, not divs: the turn's change card wraps them in a <button>,
// which may only contain phrasing content.
function GapBar({ count }: { count: number }) {
  const { t } = useTranslation("chat")
  return (
    <span className="bg-n200/50 text-n600 text-2xs block px-3 py-1 font-mono">
      {t("diff.unmodified", { count })}
    </span>
  )
}

function LineRow({ row }: { row: Extract<PreviewRow, { kind: "add" | "del" }> }) {
  const add = row.kind === "add"
  return (
    <span className={cn("flex items-baseline font-mono text-xs", add ? "bg-diffadd" : "bg-diffdel")}>
      <span className={cn("w-1 flex-none self-stretch", add ? "bg-s600" : "bg-danger")} aria-hidden />
      <span className={cn("w-6 flex-none text-center select-none", add ? "text-s700" : "text-dangerink")}>
        {add ? "+" : "−"}
      </span>
      <span className="min-w-0 flex-1 pe-3 leading-6 whitespace-pre-wrap">{row.text || " "}</span>
    </span>
  )
}

interface Props {
  rows: PreviewRow[]
  /** Changed lines the preview left out, shown as a trailing hint. */
  hidden?: number
  className?: string
}

export function DiffRows({ rows, hidden = 0, className }: Props) {
  const { t } = useTranslation("chat")
  if (rows.length === 0) return null
  return (
    <span className={cn("block overflow-hidden", className)}>
      {rows.map((row, i) =>
        row.kind === "gap" ? (
          <GapBar key={`gap-${i}`} count={row.count} />
        ) : (
          <LineRow key={`row-${i}`} row={row} />
        ),
      )}
      {hidden > 0 && (
        <span className="text-n600 text-2xs block px-3.5 py-1.5">{t("diff.more", { count: hidden })}</span>
      )}
    </span>
  )
}
