// Tab/menu glyphs and badge tone helpers, ported from the design reference.
// Glyphs are exposed as data (not JSX literals) so the i18next no-literal-string
// rule never sees them; colors resolve to token classes only.
import type { TabKind } from "@/features/workbench/stores/panel"

export const TAB_GLYPH: Record<TabKind, string> = {
  menu: "≡",
  review: "±",
  terminal: "›_",
  browser: "⊕",
  files: "▤",
  desktop: "▣",
}

export type Tone = "accent" | "sage" | "red" | "grey"

export function toneBg(tone: Tone): string {
  return tone === "accent"
    ? "bg-a100"
    : tone === "sage"
      ? "bg-s100"
      : tone === "red"
        ? "bg-dangersoft"
        : "bg-n200"
}

export function toneFg(tone: Tone): string {
  return tone === "accent"
    ? "text-a800"
    : tone === "sage"
      ? "text-s800"
      : tone === "red"
        ? "text-dangerink"
        : "text-n700"
}

const DOC_EXT = new Set(["md", "markdown", "mdx", "txt", "rst"])
const CODE_EXT = new Set([
  "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "go", "rs", "java", "kt", "c", "h",
  "cpp", "cc", "hpp", "css", "scss", "less", "json", "yml", "yaml", "toml", "sh",
  "bash", "zsh", "rb", "php", "sql", "html", "vue", "svelte", "swift", "dart",
])

export function fileExt(path: string): string {
  const base = path.split("/").pop() ?? path
  const dot = base.lastIndexOf(".")
  return dot > 0 ? base.slice(dot + 1).toLowerCase() : ""
}

export function isDocPath(path: string): boolean {
  return DOC_EXT.has(fileExt(path))
}

/** Uppercase 2–3 char badge + tone: docs→sage, code→accent, deleted→red, else grey. */
export function fileBadge(path: string, status?: "added" | "modified" | "deleted"): {
  text: string
  tone: Tone
} {
  const ext = fileExt(path)
  const base = path.split("/").pop() ?? path
  const text = (ext || base).slice(0, 3).toUpperCase()
  let tone: Tone = "grey"
  if (status === "deleted") tone = "red"
  else if (DOC_EXT.has(ext)) tone = "sage"
  else if (CODE_EXT.has(ext)) tone = "accent"
  return { text, tone }
}

/** Split a path into leading dir (with trailing slash) and base name. */
export function splitPath(path: string): { dir: string; base: string } {
  const cut = path.lastIndexOf("/")
  return cut > -1 ? { dir: path.slice(0, cut + 1), base: path.slice(cut + 1) } : { dir: "", base: path }
}
