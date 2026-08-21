// Pure parsers that turn a tool part's raw input/output/metadata into the
// structures the layout components render. No React here — every function is a
// plain data transform so it can be unit-tested in isolation.

export interface SearchResult {
  title: string
  url: string
  snippet: string
}

export interface DiffEdit {
  oldString: string
  newString: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : ""
}

/** Structured web_search results from a tool part's `metadata.results`. */
export function parseSearchResults(metadata: Record<string, unknown> | null | undefined): SearchResult[] {
  if (!isRecord(metadata) || !Array.isArray(metadata.results)) return []
  const out: SearchResult[] = []
  for (const item of metadata.results) {
    if (!isRecord(item)) continue
    const url = asString(item.url).trim()
    if (!url) continue
    out.push({
      title: asString(item.title).trim(),
      url,
      snippet: asString(item.snippet).trim(),
    })
  }
  return out
}

const URL_LINE = /^\s+URL:\s*(\S+)/gm

/** Fallback: pull URLs out of web_search's numbered plain-text output. */
export function parseSearchUrls(output: string | undefined): string[] {
  if (!output) return []
  const urls: string[] = []
  URL_LINE.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = URL_LINE.exec(output)) !== null) {
    urls.push(match[1])
  }
  return urls
}

/** Deduplicate URLs preserving first-seen order, capped for the source-pill row. */
export function dedupeUrls(urls: string[], limit = 8): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of urls) {
    const url = raw.trim()
    if (!url || seen.has(url)) continue
    seen.add(url)
    out.push(url)
    if (out.length >= limit) break
  }
  return out
}

/** Hostname for a source pill; falls back to the raw string when unparseable. */
export function safeHostname(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

const LINE_NUMBER = /^\s*\d+\t/

/** Strip the `     12\t` line-number prefix `read` prepends to every line. */
export function stripLineNumbers(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(LINE_NUMBER, ""))
    .join("\n")
}

/** old/new pairs for edit (single) and multiedit (`edits` array) inputs. */
export function parseEdits(input: Record<string, unknown> | undefined): DiffEdit[] {
  if (!input) return []
  if (Array.isArray(input.edits)) {
    const out: DiffEdit[] = []
    for (const edit of input.edits) {
      if (!isRecord(edit)) continue
      out.push({ oldString: asString(edit.old_string), newString: asString(edit.new_string) })
    }
    return out
  }
  const oldString = asString(input.old_string)
  const newString = asString(input.new_string)
  if (oldString || newString) return [{ oldString, newString }]
  return []
}

/** Bash exit code from `metadata.exit_code` (number or numeric string). */
export function parseExitCode(metadata: Record<string, unknown> | null | undefined): number | null {
  if (!isRecord(metadata)) return null
  const value = metadata.exit_code
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) return Number(value)
  return null
}

/** Whether metadata flags the output as truncated. */
export function isTruncated(metadata: Record<string, unknown> | null | undefined): boolean {
  return isRecord(metadata) && metadata.truncated === true
}
