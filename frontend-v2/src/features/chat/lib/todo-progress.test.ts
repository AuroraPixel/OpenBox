// The bar under a running task.
//
// It is invented, but it has to be invented the same way every time: two tabs
// on the same run, and a reload of either, must agree. So `now` is an input,
// and everything else comes from data that is already persisted.
import { describe, expect, it } from "vitest"
import { progressPercent, taskProgress } from "./todo-progress"

const start = "2026-08-22T00:00:00.000Z"
const began = Date.parse(start)

function at(seconds: number, steps = 0) {
  return taskProgress({ startedAt: start, steps, now: began + seconds * 1000 })
}

describe("a task that has not started", () => {
  it("shows nothing", () => {
    expect(taskProgress({ startedAt: null, steps: 0, now: began })).toBe(0)
  })

  it("shows nothing when the time is missing entirely", () => {
    expect(taskProgress({ steps: 3, now: began })).toBe(0)
  })
})

describe("a running task", () => {
  it("is visible the instant it starts", () => {
    expect(at(0)).toBeGreaterThan(0)
  })

  it("grows with time", () => {
    expect(at(60)).toBeGreaterThan(at(10))
  })

  it("grows with work done", () => {
    expect(at(10, 4)).toBeGreaterThan(at(10, 0))
  })

  it("never reaches the end, however long it runs", () => {
    expect(at(86_400, 999)).toBeLessThan(1)
    expect(at(86_400, 999)).toBeLessThanOrEqual(0.9)
  })

  it("gives the same answer for the same inputs", () => {
    // The property a reload depends on: nothing here is read from a clock.
    expect(at(42, 3)).toBe(at(42, 3))
  })

  it("does not run backwards when the clock is behind the start", () => {
    expect(taskProgress({ startedAt: start, steps: 0, now: began - 5000 })).toBeGreaterThan(0)
  })

  it("survives a start time it cannot read", () => {
    const value = taskProgress({ startedAt: "not a date", steps: 0, now: began })
    expect(value).toBeGreaterThan(0)
    expect(value).toBeLessThan(1)
  })
})

describe("showing it", () => {
  it("is a whole number of percent", () => {
    expect(progressPercent(0.456)).toBe(46)
  })

  it("never shows a full bar for an unfinished task", () => {
    expect(progressPercent(at(86_400, 999))).toBeLessThanOrEqual(90)
  })
})
