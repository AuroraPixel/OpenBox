// Per-step "done" glyphs and the running spinner glyph (design mock.* timing).
export const STEP_GLYPHS = ["⌕", "▤", "±"] as const
export const RUNNING_GLYPH = "◔"

export interface StepFrame {
  at: number
  dur: number
  ms: string
}
export interface Timeline {
  askFull: string
  cps: number
  ansFull: string
  ansCps: number
  askDone: number
  thinkAt: number
  steps: StepFrame[]
  stepsEnd: number
  answerAt: number
  answerDone: number
  period: number
  finalFrame: number
}

/**
 * Rebuilds the mock chat timeline for the active language. Character-per-ms
 * typing speeds and step timings are ported verbatim from the design so the
 * playback rhythm matches the reference.
 */
export function buildTimeline(t: (key: string) => string, isEn: boolean): Timeline {
  const askFull = t("mock.ask")
  const ansFull = t("mock.answer")
  const cps = isEn ? 15 : 46
  const ansCps = isEn ? 11 : 34

  const askDone = 260 + askFull.length * cps
  const thinkAt = askDone + 240
  const steps: StepFrame[] = [
    { at: thinkAt + 420, dur: 900, ms: "0.9s" },
    { at: thinkAt + 1420, dur: 200, ms: "0.2s" },
    { at: thinkAt + 1720, dur: 1400, ms: "1.4s" },
  ]
  const stepsEnd = steps[2].at + steps[2].dur
  const answerAt = stepsEnd + 320
  const answerDone = answerAt + ansFull.length * ansCps
  const period = answerDone + 320 + 3200

  return {
    askFull,
    cps,
    ansFull,
    ansCps,
    askDone,
    thinkAt,
    steps,
    stepsEnd,
    answerAt,
    answerDone,
    period,
    // A frame where everything is settled (past the diff, before the loop pause).
    finalFrame: answerDone + 600,
  }
}

/** Number of full characters to reveal at `ms`, clamped to the string length. */
export function typed(full: string, startAt: number, ms: number, cps: number): string {
  const n = Math.round((ms - startAt) / cps)
  return full.slice(0, Math.max(0, Math.min(full.length, n)))
}
