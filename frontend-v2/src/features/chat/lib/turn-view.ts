// Assembles one assistant turn into DEEIX-Chat's message shape: the traces are
// aggregated to the top of the turn (process → thinking → tool chain) and the
// answer prose follows as one continuous body. This is deliberately NOT an
// interleaved block sequence — the reference UI keeps exactly three collapsed
// trace rows per turn no matter how many steps ran.
import type {
  AgentSwitchPart,
  CompactionPart,
  FilePart,
  MessagePart,
  MessageReaction,
  MessageWithParts,
  PatchPart,
  PlanPart,
  RetryPart,
  SubtaskPart,
  ToolPart,
  TokenUsage,
} from "@/shared/types/api"

export interface UserTurn {
  kind: "user"
  key: string
  message: MessageWithParts
}
/** Identity + meta of the turn's *last* assistant message, so the meta bar has
 *  something to hang on after {@link mergeTurns} collapses the parts lists. */
export interface AssistantTurnMeta {
  messageId: string
  tokens?: TokenUsage | null
  reaction?: MessageReaction
  error?: Record<string, unknown> | null
  createdAt: string
}
export interface AssistantTurn {
  kind: "assistant"
  key: string
  parts: MessagePart[]
  meta: AssistantTurnMeta
}
export type Turn = UserTurn | AssistantTurn

function metaOf(m: MessageWithParts): AssistantTurnMeta {
  return {
    messageId: m.id,
    tokens: m.tokens,
    reaction: m.reaction,
    error: m.error,
    createdAt: m.created_at,
  }
}

/** Group the flat message list into user bubbles and merged assistant turns. */
export function mergeTurns(messages: MessageWithParts[]): Turn[] {
  const turns: Turn[] = []
  for (const m of messages) {
    if (m.role === "user") {
      turns.push({ kind: "user", key: m.id, message: m })
      continue
    }
    const last = turns[turns.length - 1]
    if (last && last.kind === "assistant") {
      last.parts = [...last.parts, ...m.parts]
      // Adopt the newest message's meta — reaction/tokens belong to the final
      // assistant message of the merged turn. The error is the exception: it
      // must not be erased by a message that merely carries none, or a turn
      // that failed would render as if it had succeeded and the retry
      // affordance would vanish with it.
      last.meta = { ...metaOf(m), error: m.error ?? last.meta.error }
    } else {
      turns.push({ kind: "assistant", key: m.id, parts: [...m.parts], meta: metaOf(m) })
    }
  }
  return turns
}

export type ToolLike = ToolPart | SubtaskPart
export type NoticePart = CompactionPart | RetryPart | AgentSwitchPart

export interface TurnView {
  /** Context tokens prepared for this turn (process trace subtitle). */
  contextTokens: number
  /** Concatenated reasoning text (thinking trace body). */
  thinking: string
  thinkingStreaming: boolean
  /** Every tool/subtask call of the turn (tool chain rows). */
  tools: ToolLike[]
  toolsStreaming: boolean
  /** Answer prose: all text parts joined in order. */
  content: string
  /** Trailing artifacts rendered under the body. */
  patches: PatchPart[]
  files: FilePart[]
  plans: PlanPart[]
  notices: NoticePart[]
  /** Total wall-clock of the turn's steps, seconds. */
  durationSec: number
}

function isRunning(part: ToolLike): boolean {
  return part.status === "running" || part.status === "pending"
}

export function buildTurnView(parts: MessagePart[]): TurnView {
  const view: TurnView = {
    contextTokens: 0,
    thinking: "",
    thinkingStreaming: false,
    tools: [],
    toolsStreaming: false,
    content: "",
    patches: [],
    files: [],
    plans: [],
    notices: [],
    durationSec: 0,
  }

  const reasoning: string[] = []
  const texts: string[] = []
  let lastPartType: MessagePart["type"] | null = null

  for (const p of parts) {
    switch (p.type) {
      case "reasoning":
        if (p.text.trim()) reasoning.push(p.text)
        break
      case "tool":
      case "subtask":
        view.tools.push(p)
        if (p.type === "tool" && typeof p.duration === "number") view.durationSec += p.duration
        break
      case "step-finish":
        // The context actually sent upstream for this step.
        view.contextTokens = Math.max(view.contextTokens, p.input_tokens)
        view.durationSec += p.duration
        break
      case "text":
        if (p.text) texts.push(p.text)
        break
      case "patch":
        view.patches.push(p)
        break
      case "file":
        view.files.push(p)
        break
      case "plan":
        view.plans.push(p)
        break
      case "compaction":
      case "retry":
      case "agent":
        view.notices.push(p)
        break
      case "step-start":
        break
    }
    lastPartType = p.type
  }

  view.thinking = reasoning.join("\n\n")
  view.content = texts.join("")
  view.tools.sort(() => 0)
  view.toolsStreaming = view.tools.some(isRunning)
  // Reasoning is live while it is the newest thing the model emitted.
  view.thinkingStreaming = lastPartType === "reasoning"
  return view
}
