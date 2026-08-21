import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useModelChoice } from "./useModelChoice"

// Each conversation carries its own model. Reopening one must restore what it
// was last using, and an unsent pick must not follow the user to another chat.
describe("useModelChoice", () => {
  it("prefers the session's own model over the deployment default", () => {
    const { result } = renderHook(() =>
      useModelChoice({ sessionModel: "openai/claude-opus-5", sessionKey: "a", fallback: "openai/gpt-5.6-luna" }),
    )
    expect(result.current.activeId).toBe("openai/claude-opus-5")
  })

  it("falls back to the default for a conversation that has not chosen", () => {
    const { result } = renderHook(() => useModelChoice({ sessionKey: "a", fallback: "openai/gpt-5.6-luna" }))
    expect(result.current.activeId).toBe("openai/gpt-5.6-luna")
  })

  it("a pick wins over the stored model for the rest of this conversation", () => {
    const { result } = renderHook(() =>
      useModelChoice({ sessionModel: "openai/claude-opus-5", sessionKey: "a", fallback: "x" }),
    )
    act(() => result.current.pick("openai/gpt-5.4"))
    expect(result.current.activeId).toBe("openai/gpt-5.4")
  })

  it("an unsent pick does not follow the user into another conversation", () => {
    const { result, rerender } = renderHook(
      ({ key, model }: { key: string; model?: string }) =>
        useModelChoice({ sessionModel: model, sessionKey: key, fallback: "openai/gpt-5.6-luna" }),
      { initialProps: { key: "a", model: "openai/claude-opus-5" } },
    )
    act(() => result.current.pick("openai/gpt-5.4"))
    expect(result.current.activeId).toBe("openai/gpt-5.4")

    rerender({ key: "b", model: "openai/deepseek-v4-pro" })
    expect(result.current.activeId).toBe("openai/deepseek-v4-pro")
  })
})
