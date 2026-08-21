import { describe, expect, it } from "vitest"
import { editPreview } from "./diff-preview"

describe("editPreview", () => {
  it("keeps only the changed line when context is shared", () => {
    const { rows, totalChanges } = editPreview("A\nB\nC", "A\nBB\nC")
    expect(rows).toEqual([
      { kind: "gap", count: 1 },
      { kind: "del", text: "B" },
      { kind: "add", text: "BB" },
      { kind: "gap", count: 1 },
    ])
    expect(totalChanges).toBe(2)
  })

  it("treats a pure insertion as adds only", () => {
    const { rows } = editPreview("A\nC", "A\nB\nC")
    expect(rows.filter((r) => r.kind === "del")).toHaveLength(0)
    expect(rows.filter((r) => r.kind === "add")).toEqual([{ kind: "add", text: "B" }])
  })

  it("caps long rewrites and reports the remainder", () => {
    const before = Array.from({ length: 10 }, (_, i) => `x${i}`).join("\n")
    const after = Array.from({ length: 10 }, (_, i) => `y${i}`).join("\n")
    const { hiddenChanges, totalChanges } = editPreview(before, after, 6)
    expect(totalChanges).toBe(20)
    expect(hiddenChanges).toBe(14)
  })

  it("handles creating a file from nothing", () => {
    const { rows, totalChanges } = editPreview("", "only line")
    expect(rows).toEqual([{ kind: "add", text: "only line" }])
    expect(totalChanges).toBe(1)
  })
})
