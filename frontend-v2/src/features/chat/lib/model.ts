import type { ModelInfo } from "@/shared/types/api"

/** The display name for a model id.
 *
 * Ids carry a provider prefix that is an artefact of routing, not something the
 * user chose: every model behind an OpenAI-compatible gateway is `openai/…`
 * whoever actually built it, so `openai/deepseek-v4-flash` reads as simply
 * wrong. Prefer the name the config gives it, and fall back to the last path
 * segment so an unconfigured model still shows something sane.
 */
export function modelLabel(id: string, models?: ModelInfo[]): string {
  const configured = models?.find((m) => m.id === id)?.name?.trim()
  if (configured) return configured
  return id.split("/").pop() || id
}

/** The vendors we can show a mark for; anything else falls back to a glyph. */
export type ModelBrand =
  | "openai"
  | "anthropic"
  | "deepseek"
  | "google"
  | "meta"
  | "qwen"
  | "mistral"
  | "xai"
  | "moonshot"
  | "zhipu"
  | "generic"

/** Ordered patterns: the first match wins, so the generic `openai` names go
 *  last. Matched against the model name only — see `modelBrand`. */
const BRAND_PATTERNS: ReadonlyArray<readonly [ModelBrand, RegExp]> = [
  ["anthropic", /claude|anthropic|opus|sonnet|haiku/],
  ["deepseek", /deepseek/],
  ["google", /gemini|gemma|palm|bison/],
  ["meta", /llama|meta-/],
  ["qwen", /qwen|qwq/],
  ["mistral", /mistral|mixtral|codestral|magistral/],
  ["xai", /grok/],
  ["moonshot", /moonshot|kimi/],
  ["zhipu", /\bglm|chatglm|zhipu|z-ai/],
  ["openai", /gpt|davinci|codex|openai|\bo[1-9]\b/],
]

/** Which vendor's mark belongs on a model.
 *
 *  The provider prefix is dropped before matching, because it is routing
 *  metadata rather than authorship: behind an OpenAI-compatible gateway every
 *  id reads `openai/…` no matter who built the model. Matching the whole id
 *  would put OpenAI's mark on Claude and DeepSeek — and, worse, on every
 *  unrecognised model too, since `openai` is in the prefix of all of them.
 */
export function modelBrand(id: string): ModelBrand {
  const name = (id.split("/").pop() ?? id).toLowerCase()
  for (const [brand, pattern] of BRAND_PATTERNS) {
    if (pattern.test(name)) return brand
  }
  return "generic"
}

/** How much context the given model can hold, in tokens.
 *
 * The backend resolves this per model (config override, else family default),
 * so `fallback` only covers the gap before the config query settles.
 */
export function modelContextLimit(
  id: string | undefined,
  models: ModelInfo[] | undefined,
  fallback = 0,
): number {
  if (!id) return fallback
  return models?.find((m) => m.id === id)?.context_limit || fallback
}
