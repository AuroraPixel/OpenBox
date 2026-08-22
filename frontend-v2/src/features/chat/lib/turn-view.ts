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
  TodoItem,
  TodoPart,
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
  /** Present when the turn kept a todo list; the card renders instead of the
   *  flat tool chain. */
  todo: TodoView | null
}

/** One task, with the calls made while it was the one in progress. */
export interface TodoTask {
  item: TodoItem
  tools: ToolLike[]
}

export interface TodoView {
  tasks: TodoTask[]
  /** Calls made before any task started — the model looking around before it
   *  knew what the list was. */
  before: ToolLike[]
  /** Calls made after the last task closed: tidying up, not part of a step. */
  after: ToolLike[]
  /** The heading: the running task's own wording, when it gave one. */
  activeForm: string | null
  done: number
  /** Steps that count towards the total — a cancelled task is not one. */
  total: number
  /** 1-based position of the running task, or `done` when nothing runs. */
  current: number
  allDone: boolean
}

/** The tools a todo turn shows outside the card, in order. */
export function looseTools(todo: TodoView): ToolLike[] {
  return [...todo.before, ...todo.after]
}

/** Tools the card itself accounts for; the flat chain must not repeat them. */
function isTodoTool(part: ToolLike): boolean {
  return part.type === "tool" && (part.tool === "todo_write" || part.tool === "todo_read")
}

/** Group a turn's calls under the task that was running when each was made.
 *
 *  The todo parts are snapshots in stream order, so the task in progress at
 *  any point is the one the most recent snapshot had in progress. A call
 *  before the first snapshot belongs to no task; so does one made after every
 *  task closed. Both are shown outside the card rather than forced under a
 *  step they did not belong to.
 */
function buildTodoView(parts: MessagePart[]): TodoView | null {
  const snapshots = parts.filter((p): p is TodoPart => p.type === "todo")
  if (snapshots.length === 0) return null

  const buckets = new Map<string, ToolLike[]>()
  const before: ToolLike[] = []
  const after: ToolLike[] = []
  let running: string | null = null
  let started = false

  for (const part of parts) {
    if (part.type === "todo") {
      // The model is told to keep one task in progress. When it breaks that
      // rule, the newest wins — that is the one it just moved to.
      const active = [...part.items].reverse().find((i) => i.status === "in_progress")
      running = active?.id ?? null
      if (running) started = true
      continue
    }
    if (part.type !== "tool" && part.type !== "subtask") continue
    if (isTodoTool(part)) continue
    if (running) {
      const bucket = buckets.get(running) ?? []
      bucket.push(part)
      buckets.set(running, bucket)
    } else if (started) {
      after.push(part)
    } else {
      before.push(part)
    }
  }

  const items = snapshots[snapshots.length - 1].items
  const tasks = items.map((item) => ({ item, tools: buckets.get(item.id) ?? [] }))
  const counted = items.filter((i) => i.status !== "cancelled")
  const done = counted.filter((i) => i.status === "completed").length
  const activeIndex = counted.findIndex((i) => i.status === "in_progress")
  const active = activeIndex >= 0 ? counted[activeIndex] : null

  return {
    tasks,
    before,
    after,
    activeForm: active?.active_form?.trim() || null,
    done,
    total: counted.length,
    current: activeIndex >= 0 ? activeIndex + 1 : done,
    allDone: counted.length > 0 && done === counted.length,
  }
}

function isRunning(part: ToolLike): boolean {
  return part.status === "running" || part.status === "pending"
}

/** How long a call took, in seconds, or null if it never said.
 *
 *  Two places, because the live event and the stored part disagree: the
 *  `tool.completed` event puts it on the part, while what gets persisted has
 *  it under `metadata`. Reading only the first made every duration in a
 *  reloaded conversation read as zero.
 */
export function toolDuration(part: ToolLike): number | null {
  if (part.type !== "tool") return null
  if (typeof part.duration === "number") return part.duration
  const stored = part.metadata?.duration
  return typeof stored === "number" ? stored : null
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
    todo: null,
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
        view.durationSec += toolDuration(p) ?? 0
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
      case "todo":
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

  view.todo = buildTodoView(parts)
  if (view.todo) {
    // The card accounts for every call it filed under a task, so the flat
    // chain keeps only what fell outside — and drops the todo bookkeeping
    // calls, which the card *is*. Turns without a card are untouched: those
    // rows are the only trace those sessions have.
    view.tools = looseTools(view.todo)
    view.toolsStreaming = view.tools.some(isRunning)
  }
  return view
}
