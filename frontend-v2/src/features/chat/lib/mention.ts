// Pure trigger detection / replacement for the composer's @ / mention menu.
// No React, no I/O — unit-testable in isolation.
//
//   resolveTrigger(text, caret) → active trigger at the caret, or null
//   replaceTrigger(text, range, insert) → text with the trigger span replaced
//
// Rules (see task spec):
//   - "@" fires at a word boundary (line start, or after whitespace / an
//     opening bracket / CJK char / punctuation).
//   - "/" fires only at the start of a line or the start of the whole text.
//   - The query runs from the trigger char to the caret; any whitespace inside
//     it invalidates the trigger, and a query longer than 40 chars is dropped.

export type MentionKind = "at" | "slash"

export interface MentionTrigger {
  kind: MentionKind
  /** Query text between the trigger char and the caret (may be empty). */
  query: string
  /** Index of the trigger char ("@" or "/") in `text`. */
  start: number
  /** Caret index (exclusive end of the replaced span). */
  end: number
}

export interface MentionRange {
  start: number
  end: number
}

const MAX_QUERY = 40

// Chars that count as a left boundary for an "@" mention: ASCII punctuation,
// CJK symbols/punctuation (U+3000–303F), fullwidth forms (U+FF00–FFEF), and
// CJK ideographs (U+3400–9FFF). Written with \u escapes to stay ASCII-clean.
const BOUNDARY = /[[({<,.!?;:'"`\u3000-\u303f\u3400-\u9fff\uff00-\uffef]/

function isAtBoundary(text: string, index: number): boolean {
  if (index === 0) return true
  const prev = text[index - 1] ?? ""
  return /\s/.test(prev) || BOUNDARY.test(prev)
}

function isLineStart(text: string, index: number): boolean {
  return index === 0 || text[index - 1] === "\n"
}

export function resolveTrigger(text: string, caret: number): MentionTrigger | null {
  const end = Math.min(Math.max(caret, 0), text.length)

  // Any whitespace between the trigger char and the caret invalidates the
  // query, so the active trigger must sit inside the whitespace-free run that
  // ends at the caret. Find that run's start first.
  let runStart = end
  while (runStart > 0 && !/\s/.test(text[runStart - 1] ?? "")) runStart--

  // Within the run, the *leftmost* trigger char that satisfies its boundary
  // rule wins. This keeps "@src/foo" an "@" mention even though the path holds
  // a "/", instead of letting that inner "/" (which fails the line-start rule)
  // swallow the trigger.
  for (let i = runStart; i < end; i++) {
    const ch = text[i]
    if (ch !== "@" && ch !== "/") continue
    const kind: MentionKind = ch === "@" ? "at" : "slash"
    if (kind === "at" ? !isAtBoundary(text, i) : !isLineStart(text, i)) continue

    const query = text.slice(i + 1, end)
    if (query.length > MAX_QUERY) return null
    return { kind, query, start: i, end }
  }

  return null
}

export function replaceTrigger(
  text: string,
  range: MentionRange,
  insert: string,
): { text: string; caret: number } {
  const before = text.slice(0, range.start)
  const after = text.slice(range.end)
  // Always leave a single trailing space so the next token starts cleanly.
  const trailing = after.startsWith(" ") ? "" : " "
  const chunk = `${insert}${trailing}`
  return { text: `${before}${chunk}${after}`, caret: range.start + chunk.length }
}
