// Turns a tool's edit into a short preview: only changed lines survive, and
// every run of untouched context collapses into one "N unmodified lines" bar.
// Pure, so it can be unit tested.

export interface ChangeRow {
  kind: "add" | "del"
  text: string
}
export interface GapRow {
  kind: "gap"
  count: number
}
export type PreviewRow = ChangeRow | GapRow

export interface DiffPreview {
  rows: PreviewRow[]
  /** Changed lines that did not fit in the preview. */
  hiddenChanges: number
  totalChanges: number
}

function pushGap(rows: PreviewRow[], count: number): void {
  if (count <= 0) return
  const last = rows[rows.length - 1]
  if (last && last.kind === "gap") {
    last.count += count
    return
  }
  rows.push({ kind: "gap", count })
}

/**
 * Preview rows for an in-place edit, built from the tool's own
 * old_string/new_string. Shared leading/trailing lines collapse into gap bars
 * so a one-line change inside a big block reads as one line, not two blocks.
 */
export function editPreview(oldText: string, newText: string, maxChanges = 8): DiffPreview {
  const before = oldText.length > 0 ? oldText.split("\n") : []
  const after = newText.length > 0 ? newText.split("\n") : []

  let head = 0
  while (head < before.length && head < after.length && before[head] === after[head]) head += 1

  let tail = 0
  while (
    tail < before.length - head &&
    tail < after.length - head &&
    before[before.length - 1 - tail] === after[after.length - 1 - tail]
  ) {
    tail += 1
  }

  const removed = before.slice(head, before.length - tail)
  const added = after.slice(head, after.length - tail)
  const total = removed.length + added.length

  const rows: PreviewRow[] = []
  pushGap(rows, head)
  let shown = 0
  for (const text of removed) {
    if (shown >= maxChanges) break
    rows.push({ kind: "del", text })
    shown += 1
  }
  for (const text of added) {
    if (shown >= maxChanges) break
    rows.push({ kind: "add", text })
    shown += 1
  }
  if (rows.length > 0) pushGap(rows, tail)

  return { rows, hiddenChanges: Math.max(0, total - shown), totalChanges: total }
}
