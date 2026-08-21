import { describe, expect, it } from "vitest"
import type { ModelInfo } from "@/shared/types/api"
import { modelBrand, modelContextLimit, modelLabel } from "./model"

// What the gateway actually returns: everything prefixed `openai/`, whoever
// built the model. That prefix is the trap both helpers exist to avoid.
const MODELS: ModelInfo[] = [
  { id: "openai/gpt-5.6-luna", name: "GPT-5.6 Luna", provider: "openai", context_limit: 256000 },
  { id: "openai/claude-opus-5", name: "Claude Opus 5", provider: "openai", context_limit: 1000000 },
  { id: "openai/deepseek-v4-flash", name: "DeepSeek V4 Flash", provider: "openai" },
]

describe("modelLabel", () => {
  it("prefers the configured display name", () => {
    expect(modelLabel("openai/claude-opus-5", MODELS)).toBe("Claude Opus 5")
  })

  it("strips the routing prefix from a model the config does not list", () => {
    // A session pinned to a retired model still has to read as a name.
    expect(modelLabel("openai/gemini-3.7-flash", MODELS)).toBe("gemini-3.7-flash")
  })

  it("falls back to the id when there is nothing to strip", () => {
    expect(modelLabel("mystery-model", [])).toBe("mystery-model")
  })
})

describe("modelBrand", () => {
  it("reads the model name, not the provider prefix", () => {
    expect(modelBrand("openai/claude-opus-5")).toBe("anthropic")
    expect(modelBrand("openai/deepseek-v4-flash")).toBe("deepseek")
    expect(modelBrand("openai/gemini-3.7-flash")).toBe("google")
  })

  it("still recognises genuine OpenAI models", () => {
    expect(modelBrand("openai/gpt-5.6-luna")).toBe("openai")
    expect(modelBrand("openai/gpt-5.3-codex")).toBe("openai")
  })

  it("does not stamp OpenAI on an unknown model just because of the prefix", () => {
    // The whole point: `openai/` is in every id here, so matching the full id
    // would give a vendor we have never heard of OpenAI's trademark.
    expect(modelBrand("openai/some-new-vendor-model")).toBe("generic")
  })

  it("resolves the other vendors it knows", () => {
    expect(modelBrand("meta/llama-4-scout")).toBe("meta")
    expect(modelBrand("alibaba/qwen3-max")).toBe("qwen")
    expect(modelBrand("xai/grok-5")).toBe("xai")
    expect(modelBrand("moonshot/kimi-k2")).toBe("moonshot")
  })
})

describe("modelContextLimit", () => {
  it("uses the configured window", () => {
    expect(modelContextLimit("openai/gpt-5.6-luna", MODELS)).toBe(256000)
  })

  it("falls back when the model has no window of its own", () => {
    // Covers a session pinned to a model the config dropped: the ring should
    // still measure something, using whatever the last run actually used.
    expect(modelContextLimit("openai/gemini-3.7-flash", MODELS, 1000000)).toBe(1000000)
    expect(modelContextLimit("openai/deepseek-v4-flash", MODELS, 900)).toBe(900)
  })

  it("returns the fallback when no model is selected yet", () => {
    expect(modelContextLimit(undefined, MODELS, 0)).toBe(0)
  })
})
