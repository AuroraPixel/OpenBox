// Lightweight syntax highlighter — ported from the design reference's tokenize()
// into a pure function. Emits spans carrying a token *class* (never inline color):
// comment→n500 italic, string→s700, number→a700, Uppercase→n700, keyword→a700.
export interface Token {
  text: string
  className: string
}

const DEFAULT_CLASS = "text-n900"

const KEYWORDS =
  "import|from|export|default|const|let|var|await|async|function|return|new|type|interface|class|if|else|true|false|null|undefined"

function pattern(): RegExp {
  return new RegExp(
    `(\\/\\/[^\\n]*|"(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*'|\`[^\`]*\`|\\b(?:${KEYWORDS})\\b|\\b[A-Z][A-Za-z0-9_]*\\b|\\b\\d+(?:\\.\\d+)*\\b)`,
    "g",
  )
}

function classify(token: string): string {
  if (token.startsWith("//")) return "text-n500 italic"
  const first = token[0]
  if (first === '"' || first === "'" || first === "`") return "text-s700"
  if (/^\d/.test(token)) return "text-a700"
  if (/^[A-Z]/.test(token)) return "text-n700"
  return "text-a700"
}

export function tokenize(line: string): Token[] {
  const re = pattern()
  const out: Token[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) out.push({ text: line.slice(last, m.index), className: DEFAULT_CLASS })
    out.push({ text: m[0], className: classify(m[0]) })
    last = m.index + m[0].length
  }
  if (last < line.length) out.push({ text: line.slice(last), className: DEFAULT_CLASS })
  if (out.length === 0) out.push({ text: " ", className: DEFAULT_CLASS })
  return out
}
