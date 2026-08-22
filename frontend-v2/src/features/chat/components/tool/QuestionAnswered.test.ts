// Pairing what was asked with what was chosen.
//
// The pairing used to be recoverable only by parsing quotes back out of the
// prose the model reads, so the conversation showed "Asked 2 questions" and
// nothing about which way they were decided.
import { describe, expect, it } from "vitest"
import type { ToolPart } from "@/shared/types/api"
import { questionPairs } from "./QuestionAnswered"

function part(metadata: Record<string, unknown> | null): ToolPart {
  return { type: "tool", id: "t1", tool: "question", status: "completed", metadata }
}

describe("reading a question tool's record", () => {
  it("pairs each question with its answer", () => {
    expect(
      questionPairs(part({ questions: ["Cache?", "TTL?"], answers: [["Redis"], ["15m"]] })),
    ).toEqual([
      { question: "Cache?", answer: ["Redis"] },
      { question: "TTL?", answer: ["15m"] },
    ])
  })

  it("keeps every label of a multi-select answer", () => {
    const [pair] = questionPairs(part({ questions: ["Which?"], answers: [["a", "b"]] }))
    expect(pair.answer).toEqual(["a", "b"])
  })

  it("shows a question that went unanswered rather than dropping it", () => {
    const [pair] = questionPairs(part({ questions: ["Skipped?"], answers: [[]] }))
    expect(pair).toEqual({ question: "Skipped?", answer: [] })
  })

  it("survives an answer list shorter than the questions", () => {
    const pairs = questionPairs(part({ questions: ["a", "b"], answers: [["yes"]] }))
    expect(pairs.map((p) => p.answer)).toEqual([["yes"], []])
  })

  it("has nothing to show for a part with no record", () => {
    expect(questionPairs(part(null))).toEqual([])
    expect(questionPairs(part({}))).toEqual([])
  })

  it("ignores a malformed payload instead of throwing", () => {
    expect(questionPairs(part({ questions: "not-a-list", answers: 7 }))).toEqual([])
  })
})
