// Minimal block splitter for the Files doc view — enough to honour the design's
// docStyle (h1 / paragraph / fenced code). Not a full Markdown renderer; the
// viewer is deliberately "简易".
export type DocBlockKind = "h1" | "code" | "p"

export interface DocBlock {
  kind: DocBlockKind
  text: string
}

export function toDocBlocks(content: string): DocBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n")
  const blocks: DocBlock[] = []
  let para: string[] = []
  let code: string[] | null = null

  const flushPara = () => {
    if (para.length) {
      blocks.push({ kind: "p", text: para.join(" ").trim() })
      para = []
    }
  }

  for (const line of lines) {
    if (code !== null) {
      if (line.trim().startsWith("```")) {
        blocks.push({ kind: "code", text: code.join("\n") })
        code = null
      } else {
        code.push(line)
      }
      continue
    }
    if (line.trim().startsWith("```")) {
      flushPara()
      code = []
      continue
    }
    if (/^#{1,6}\s+/.test(line)) {
      flushPara()
      blocks.push({ kind: "h1", text: line.replace(/^#{1,6}\s+/, "").trim() })
      continue
    }
    if (line.trim() === "") {
      flushPara()
      continue
    }
    para.push(line.trim())
  }
  if (code !== null) blocks.push({ kind: "code", text: code.join("\n") })
  flushPara()
  return blocks
}
