import { describe, expect, it, vi } from "vitest"

vi.mock("@/shared/i18n", () => ({ default: { language: "en-US" } }))

const { formatBytes, formatDuration, formatTokens } = await import("./format")

describe("formatBytes", () => {
  it("handles zero", () => {
    expect(formatBytes(0)).toBe("0 B")
  })
  it("scales units", () => {
    expect(formatBytes(1024)).toBe("1 KB")
    expect(formatBytes(2_516_582)).toBe("2.4 MB")
  })
  it("caps at GB", () => {
    expect(formatBytes(5 * 1024 ** 4)).toMatch(/GB$/)
  })
})

describe("formatDuration", () => {
  it("sub-10s keeps one decimal", () => {
    expect(formatDuration(4.63)).toBe("4.6s")
  })
  it("sub-minute rounds", () => {
    expect(formatDuration(42.4)).toBe("42s")
  })
  it("minutes split", () => {
    expect(formatDuration(96)).toBe("1m 36s")
  })
})

describe("formatTokens", () => {
  it("keeps small numbers", () => {
    expect(formatTokens(842)).toBe("842")
  })
  it("abbreviates thousands", () => {
    expect(formatTokens(12_400)).toBe("12.4k")
  })
})
