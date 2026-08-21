// Visual classification for tool calls — the code-side of the design's
// mapEntries / toneBg / toneFg / linePfx / lineStyle rules, expressed with
// design-token Tailwind classes only. Labels resolve through i18n `chat:kind.*`.
import type { ToolPart } from "@/shared/types/api"

export type Tone = "accent" | "sage" | "grey" | "red"

export const toneBgClass: Record<Tone, string> = {
  accent: "bg-a100",
  sage: "bg-s100",
  grey: "bg-n200",
  red: "bg-dangersoft",
}
export const toneFgClass: Record<Tone, string> = {
  accent: "text-a800",
  sage: "text-s800",
  grey: "text-n700",
  red: "text-dangerink",
}

export interface ToolGlyph {
  /** i18n key under `chat:kind.*`. */
  kindKey: string
  glyph: string
  tone: Tone
}

const BASH: ToolGlyph = { kindKey: "bash", glyph: "$", tone: "accent" }
const READ: ToolGlyph = { kindKey: "read", glyph: "▤", tone: "grey" }
const GLOB: ToolGlyph = { kindKey: "glob", glyph: "⌕", tone: "accent" }
const GREP: ToolGlyph = { kindKey: "grep", glyph: "⌕", tone: "accent" }
const EDIT: ToolGlyph = { kindKey: "edit", glyph: "✎", tone: "sage" }
const WRITE: ToolGlyph = { kindKey: "write", glyph: "✎", tone: "sage" }
const SKILL: ToolGlyph = { kindKey: "skill", glyph: "✦", tone: "sage" }
const WEB_SEARCH: ToolGlyph = { kindKey: "webSearch", glyph: "⌕", tone: "accent" }
const WEB_FETCH: ToolGlyph = { kindKey: "webFetch", glyph: "↗", tone: "accent" }
const TASK: ToolGlyph = { kindKey: "task", glyph: "⚒", tone: "sage" }
const TODO: ToolGlyph = { kindKey: "todo", glyph: "☑", tone: "sage" }
const MCP: ToolGlyph = { kindKey: "mcp", glyph: "⚒", tone: "sage" }

const TOOL_TABLE: Record<string, ToolGlyph> = {
  bash: BASH,
  shell: BASH,
  terminal: BASH,
  read: READ,
  readfile: READ,
  cat: READ,
  view: READ,
  glob: GLOB,
  find: GLOB,
  ls: GLOB,
  grep: GREP,
  search: GREP,
  ripgrep: GREP,
  edit: EDIT,
  multiedit: EDIT,
  apply_patch: EDIT,
  str_replace: EDIT,
  write: WRITE,
  writefile: WRITE,
  create: WRITE,
  new_file: WRITE,
  skill: SKILL,
  web_search: WEB_SEARCH,
  websearch: WEB_SEARCH,
  web_fetch: WEB_FETCH,
  webfetch: WEB_FETCH,
  fetch: WEB_FETCH,
  task: TASK,
  agent: TASK,
  subtask: TASK,
  todowrite: TODO,
  todo: TODO,
}

/** Structural layout for a tool's detail column — how its output is composed. */
export type ToolLayout = "search" | "fetch" | "shell" | "file" | "find" | "agent" | "skill" | "generic"

const FILE_TOOLS = ["read", "write", "edit", "multiedit", "apply_patch", "str_replace", "readfile", "writefile", "view", "create", "new_file"]
const FIND_TOOLS = ["glob", "grep", "find", "search", "ls", "ripgrep"]

/** Pick the detail-column layout for a raw tool name (mcp_* → generic). */
export function resolveToolLayout(tool: string): ToolLayout {
  const t = tool.toLowerCase()
  if (t === "web_search" || t === "websearch") return "search"
  if (t === "web_fetch" || t === "webfetch" || t === "fetch") return "fetch"
  if (t === "bash" || t === "shell" || t === "terminal") return "shell"
  if (FILE_TOOLS.includes(t)) return "file"
  if (FIND_TOOLS.includes(t)) return "find"
  // A skill load injects a whole instruction document; rendering it in the
  // transcript buries the conversation under the manual. The name is the only
  // part a reader needs.
  if (t === "skill" || t.startsWith("skill")) return "skill"
  if (t === "task" || t === "agent") return "agent"
  return "generic"
}

/** Map a raw tool name to its kind label, glyph and tone. */
export function describeTool(tool: string): ToolGlyph {
  const t = tool.toLowerCase()
  const hit = TOOL_TABLE[t]
  if (hit) return hit
  if (t.startsWith("skill")) return SKILL
  // mcp_* and everything else
  return MCP
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.length > 0 ? v : undefined
}

/** The most informative field of a tool's input, for the mono target line. */
export function toolTarget(part: ToolPart): string {
  const input = part.input ?? {}
  const t = part.tool.toLowerCase()
  if (t === "bash" || t === "shell" || t === "terminal") return str(input.command) ?? part.tool
  if (["read", "edit", "write", "multiedit", "readfile", "writefile", "view"].includes(t))
    return str(input.file_path) ?? str(input.path) ?? part.title ?? part.tool
  if (["glob", "grep", "search", "find"].includes(t))
    return str(input.pattern) ?? str(input.query) ?? part.title ?? part.tool
  if (t === "web_search" || t === "websearch") return str(input.query) ?? part.title ?? part.tool
  if (t === "web_fetch" || t === "webfetch" || t === "fetch") return str(input.url) ?? part.title ?? part.tool
  return part.title ?? str(input.description) ?? part.tool
}

export type LineKind = "cmd" | "out" | "del" | "key" | "path"

export interface ToolLine {
  kind: LineKind
  text: string
}

const OUTPUT_CAP = 12

function safeJson(input: Record<string, unknown>): string {
  try {
    const s = JSON.stringify(input)
    return s.length > 240 ? `${s.slice(0, 240)}…` : s
  } catch {
    return ""
  }
}

/** Compact one-line preview of a request input (permission card, etc.). */
export function previewInput(input?: Record<string, unknown>): string {
  if (!input || Object.keys(input).length === 0) return ""
  return safeJson(input)
}

/** Expanded body of a tool entry: an input echo plus a capped output/error tail. */
export function toolLines(part: ToolPart): ToolLine[] {
  const lines: ToolLine[] = []
  const input = part.input ?? {}
  const t = part.tool.toLowerCase()
  const hasNamedTarget = [
    "bash",
    "shell",
    "terminal",
    "read",
    "edit",
    "write",
    "multiedit",
    "readfile",
    "writefile",
    "view",
    "glob",
    "grep",
    "search",
    "find",
    "web_search",
    "websearch",
    "web_fetch",
    "webfetch",
    "fetch",
  ].includes(t)

  if (t === "bash" || t === "shell" || t === "terminal") {
    const cmd = str(input.command)
    if (cmd) lines.push({ kind: "cmd", text: cmd })
  } else if (!hasNamedTarget && Object.keys(input).length > 0) {
    lines.push({ kind: "key", text: safeJson(input) })
  }

  const body = part.error ?? part.output
  if (body) {
    const kind: LineKind = part.error ? "del" : "out"
    for (const raw of body.split("\n").slice(0, OUTPUT_CAP)) lines.push({ kind, text: raw })
  }
  return lines
}

export function linePrefix(kind: LineKind): string {
  if (kind === "cmd") return "$"
  if (kind === "del") return "−"
  if (kind === "path") return "·"
  return ""
}

/** Design-token class stack for a rendered output line. */
export function lineClass(kind: LineKind): string {
  const mono = "font-mono text-sm leading-[1.75] rounded-sm"
  if (kind === "cmd") return `${mono} px-1 font-medium text-a700`
  if (kind === "del") return `${mono} px-1 bg-dangersoft text-dangerink`
  if (kind === "key") return `${mono} px-1 bg-n200 text-n700`
  if (kind === "path") return `${mono} px-1 text-n600`
  return `${mono} px-1 text-n800`
}
