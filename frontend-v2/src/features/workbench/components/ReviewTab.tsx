// Review tab: this turn's diff as expandable file cards. Approve/reject are
// intentionally omitted (no backend capability). The expanded file is
// store.reviewFile, defaulting to the first entry.
import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { usePanelStore } from "@/features/workbench/stores/panel"
import { fileBadge, splitPath, toneBg, toneFg } from "@/features/workbench/utils/glyphs"
import { useDiffQuery } from "@/features/workbench/api/diff"
import { Spinner } from "@/shared/ui/Spinner"
import { EmptyState } from "./EmptyState"
import type { DiffEntry, DiffHunk, DiffLine } from "@/shared/types/api"

type Row = { kind: "gap"; count: number } | { kind: "line"; line: DiffLine }

function buildRows(hunks: DiffHunk[]): Row[] {
  const rows: Row[] = []
  hunks.forEach((h, i) => {
    if (i > 0) {
      const prev = hunks[i - 1]
      const gap = h.old_start - (prev.old_start + prev.old_count)
      if (gap > 0) rows.push({ kind: "gap", count: gap })
    }
    for (const line of h.lines) rows.push({ kind: "line", line })
  })
  return rows
}

function lineNo(line: DiffLine): number | string {
  const n = line.type === "del" ? line.old_line : (line.new_line ?? line.old_line)
  return n ?? ""
}

function DiffRow({ line }: { line: DiffLine }) {
  const add = line.type === "add"
  const del = line.type === "del"
  return (
    <div className={cn("flex items-baseline leading-relaxed", add && "bg-diffadd", del && "bg-diffdel")}>
      <span className="w-10.5 flex-none select-none pe-2.5 text-end font-mono text-xs text-n500">
        {lineNo(line)}
      </span>
      <span className={cn("w-4 flex-none font-mono text-sm", add ? "text-s700" : del ? "text-dangerink" : "text-transparent")}>
        {add ? "+" : del ? "−" : ""}
      </span>
      <span className="whitespace-pre font-mono text-sm text-n900">{line.content}</span>
    </div>
  )
}

function ReviewCard({ entry, open }: { entry: DiffEntry; open: boolean }) {
  const { t } = useTranslation("workbench")
  const setReviewFile = usePanelStore((s) => s.setReviewFile)
  const openKind = usePanelStore((s) => s.openKind)
  const { dir, base } = splitPath(entry.path)
  const badge = fileBadge(entry.path, entry.status)
  const skipped =
    entry.status === "added" ? t("review.skippedNew") : entry.status === "deleted" ? t("review.skippedDeleted") : ""
  const rows = buildRows(entry.hunks ?? [])
  const ref = useRef<HTMLDivElement>(null)

  // Arriving from a chat change card selects a file that may be below the
  // fold — without this the panel looks like it ignored the click.
  useEffect(() => {
    if (open) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  }, [open])

  return (
    <div ref={ref} className="overflow-hidden rounded-2xl border border-hair bg-card">
      <button
        type="button"
        onClick={() => setReviewFile(entry.path)}
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 px-4 py-2.5 text-start"
      >
        <span className={cn("flex h-5 w-6.5 flex-none items-center justify-center rounded-sm font-mono text-2xs font-semibold", toneBg(badge.tone), toneFg(badge.tone))}>
          {badge.text}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          <span className="text-n600">{dir}</span>
          <span className="font-medium">{base}</span>
        </span>
        <span className="flex-none font-mono text-xs text-s700">{`+${entry.additions}`}</span>
        <span className="flex-none font-mono text-xs text-danger">{`−${entry.deletions}`}</span>
      </button>
      {open && (
        <div className="flex flex-col border-t border-hair">
          {skipped && <div className="px-4 py-1.5 text-xs text-n600">{skipped}</div>}
          <div className="scr overflow-x-auto">
            <div className="min-w-max">
              {rows.map((r, i) =>
                r.kind === "gap" ? (
                  <div key={i} className="px-4 py-1 text-xs text-n600">
                    {t("review.unchanged", { count: r.count })}
                  </div>
                ) : (
                  <DiffRow key={i} line={r.line} />
                ),
              )}
            </div>
          </div>
          <div className="flex gap-4 px-4 py-3">
            <button
              type="button"
              onClick={() => openKind("files", { openFile: entry.path })}
              className="text-xs text-a700 hover:underline"
            >
              {t("review.openInFiles")}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Placeholder cards for the first fetch. Without it the tab renders its real
 *  header over an empty list, which reads as "the panel opened with nothing in
 *  it" rather than "still loading". */
function ReviewSkeleton({ title }: { title: string }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col" aria-busy="true">
      <div className="flex flex-none items-center gap-2.5 px-4 pb-3">
        <span className="text-sm font-medium">{title}</span>
        <Spinner className="size-3.5" />
      </div>
      <div className="flex flex-col gap-2.5 px-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-11 animate-pulse rounded-2xl border border-hair bg-n200/40" />
        ))}
      </div>
    </div>
  )
}

interface ReviewTabProps {
  sessionId: string | null
}

export function ReviewTab({ sessionId }: ReviewTabProps) {
  const { t } = useTranslation("workbench")
  const reviewFile = usePanelStore((s) => s.reviewFile)
  const openKind = usePanelStore((s) => s.openKind)
  const { data, isLoading } = useDiffQuery(sessionId)
  const entries = data ?? []

  if (isLoading) return <ReviewSkeleton title={t("review.lastChanges")} />
  if (entries.length === 0) {
    return <EmptyState title={t("review.empty")} hint={t("review.emptyHint")} />
  }

  const expandedPath = reviewFile ?? entries[0]?.path ?? null
  const totalAdd = entries.reduce((a, e) => a + e.additions, 0)
  const totalDel = entries.reduce((a, e) => a + e.deletions, 0)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-none items-center gap-2.5 px-4 pb-3">
        <span className="text-sm font-medium">{t("review.lastChanges")}</span>
        <span className="font-mono text-xs text-s700">{`+${totalAdd}`}</span>
        <span className="font-mono text-xs text-danger">{`−${totalDel}`}</span>
        {expandedPath && (
          <button
            type="button"
            onClick={() => openKind("files", { openFile: expandedPath })}
            className="ms-auto text-xs text-a700 hover:underline"
          >
            {t("review.openInFiles")}
          </button>
        )}
      </div>
      <div className="scr flex min-h-0 flex-1 flex-col gap-2.5 overflow-auto px-3 pb-3.5">
        {entries.map((entry) => (
          <ReviewCard key={entry.path} entry={entry} open={entry.path === expandedPath} />
        ))}
      </div>
    </div>
  )
}
