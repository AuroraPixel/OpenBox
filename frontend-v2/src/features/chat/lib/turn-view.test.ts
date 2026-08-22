// Filing a turn's calls under the task each belonged to.
//
// The todo parts are snapshots in stream order, so everything here is about
// reading that order correctly — including when the model breaks its own
// rule about one task at a time.
import { describe, expect, it } from "vitest"
import type { MessagePart, TodoItem, ToolPart } from "@/shared/types/api"
import { buildTurnView, mergeTurns, toolDuration } from "./turn-view"

let seq = 0
function tool(name: string, extra: Partial<ToolPart> = {}): ToolPart {
  seq += 1
  return { type: "tool", id: `t${seq}`, tool: name, status: "completed", ...extra }
}
function item(id: string, subject: string, status: TodoItem["status"] = "pending"): TodoItem {
  return { id, subject, status }
}
function todo(items: TodoItem[]): MessagePart {
  seq += 1
  return { type: "todo", id: `d${seq}`, items }
}

const A = "a"
const B = "b"

describe("a turn without a todo list", () => {
  it("has no card", () => {
    expect(buildTurnView([tool("bash")]).todo).toBeNull()
  })

  it("keeps its todo bookkeeping calls in the chain", () => {
    // These sessions have no card to show them in, so hiding them would
    // erase the only trace of the activity.
    const view = buildTurnView([tool("todo_write"), tool("bash")])
    expect(view.tools.map((p) => (p as ToolPart).tool)).toEqual(["todo_write", "bash"])
  })
})

describe("filing calls under tasks", () => {
  it("puts a call under the task that was running", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress"), item(B, "second")]),
      tool("bash"),
    ])
    expect(view.todo!.tasks[0].tools).toHaveLength(1)
    expect(view.todo!.tasks[1].tools).toHaveLength(0)
  })

  it("moves to the next task when the list says so", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress"), item(B, "second")]),
      tool("read"),
      todo([item(A, "first", "completed"), item(B, "second", "in_progress")]),
      tool("write"),
    ])
    const [first, second] = view.todo!.tasks
    expect((first.tools[0] as ToolPart).tool).toBe("read")
    expect((second.tools[0] as ToolPart).tool).toBe("write")
  })

  it("shows calls made before the list existed outside the card", () => {
    const view = buildTurnView([tool("glob"), todo([item(A, "first", "in_progress")])])
    expect(view.todo!.before.map((p) => (p as ToolPart).tool)).toEqual(["glob"])
    expect(view.todo!.tasks[0].tools).toHaveLength(0)
  })

  it("shows calls made after every task closed outside the card", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress")]),
      tool("read"),
      todo([item(A, "first", "completed")]),
      tool("bash"),
    ])
    expect(view.todo!.after.map((p) => (p as ToolPart).tool)).toEqual(["bash"])
  })

  it("hides the todo bookkeeping calls, which the card itself is", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress")]),
      tool("todo_write"),
      tool("todo_read"),
      tool("bash"),
    ])
    expect(view.todo!.tasks[0].tools).toHaveLength(1)
    expect(view.tools).toHaveLength(0)
  })

  it("leaves the chain holding exactly what the card did not", () => {
    const view = buildTurnView([
      tool("glob"),
      todo([item(A, "first", "in_progress")]),
      tool("read"),
      todo([item(A, "first", "completed")]),
      tool("bash"),
    ])
    expect(view.tools.map((p) => (p as ToolPart).tool)).toEqual(["glob", "bash"])
  })

  it("takes the newest when the model runs two tasks at once", () => {
    // Against instruction, but it happens; the newest is the one it just
    // moved to, so that is where the next call belongs.
    const view = buildTurnView([
      todo([item(A, "first", "in_progress"), item(B, "second", "in_progress")]),
      tool("bash"),
    ])
    expect(view.todo!.tasks[0].tools).toHaveLength(0)
    expect(view.todo!.tasks[1].tools).toHaveLength(1)
  })

  it("closes the window when a running task is cancelled", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress")]),
      tool("read"),
      todo([item(A, "first", "cancelled")]),
      tool("bash"),
    ])
    expect(view.todo!.tasks[0].tools).toHaveLength(1)
    expect(view.todo!.after).toHaveLength(1)
  })

  it("reads the task list from the newest snapshot", () => {
    const view = buildTurnView([
      todo([item(A, "first", "in_progress")]),
      todo([item(A, "first", "completed"), item(B, "added later")]),
    ])
    expect(view.todo!.tasks.map((t) => t.item.subject)).toEqual(["first", "added later"])
  })
})

describe("counting steps", () => {
  it("numbers the running task", () => {
    const view = buildTurnView([
      todo([item(A, "first", "completed"), item(B, "second", "in_progress")]),
    ])
    expect(view.todo!.current).toBe(2)
    expect(view.todo!.total).toBe(2)
  })

  it("does not count a cancelled task as a step", () => {
    const view = buildTurnView([
      todo([item(A, "first", "completed"), item(B, "dropped", "cancelled")]),
    ])
    expect(view.todo!.total).toBe(1)
    expect(view.todo!.allDone).toBe(true)
  })

  it("is not finished while a task is still pending", () => {
    const view = buildTurnView([todo([item(A, "first", "completed"), item(B, "second")])])
    expect(view.todo!.allDone).toBe(false)
  })

  it("is not finished when the list is empty", () => {
    expect(buildTurnView([todo([])]).todo!.allDone).toBe(false)
  })

  it("uses the running task's own wording as the heading", () => {
    const running: TodoItem = {
      id: A,
      subject: "Compute the split",
      status: "in_progress",
      active_form: "Computing the split",
    }
    expect(buildTurnView([todo([running])]).todo!.activeForm).toBe("Computing the split")
  })

  it("has no heading of its own when nothing is running", () => {
    expect(buildTurnView([todo([item(A, "first")])]).todo!.activeForm).toBeNull()
  })
})

describe("how long a call took", () => {
  it("reads what the live event put on the part", () => {
    expect(toolDuration(tool("bash", { duration: 1.5 }))).toBe(1.5)
  })

  it("falls back to what was stored, which is where a reload finds it", () => {
    expect(toolDuration(tool("bash", { metadata: { duration: 2.5 } }))).toBe(2.5)
  })

  it("is null when neither says", () => {
    expect(toolDuration(tool("bash"))).toBeNull()
  })
})

describe("merging messages into turns", () => {
  it("keeps a turn's error when a later message carries none", () => {
    const turns = mergeTurns([
      { id: "1", session_id: "s", role: "assistant", parts: [], created_at: "", error: { m: 1 } },
      { id: "2", session_id: "s", role: "assistant", parts: [], created_at: "" },
    ])
    expect(turns[0].kind === "assistant" && turns[0].meta.error).toEqual({ m: 1 })
  })

  it("keeps parts in order across the messages of one turn", () => {
    const turns = mergeTurns([
      { id: "1", session_id: "s", role: "assistant", parts: [tool("read")], created_at: "" },
      { id: "2", session_id: "s", role: "assistant", parts: [tool("write")], created_at: "" },
    ])
    const parts = turns[0].kind === "assistant" ? turns[0].parts : []
    expect(parts.map((p) => (p as ToolPart).tool)).toEqual(["read", "write"])
  })
})

describe("a real recorded run", () => {
  // Taken verbatim from a live turn: the model planned four tasks and
  // interleaved todo_write with the work, which is the shape the card is
  // built for. Kept as a fixture because every rule above is tested in
  // isolation, and this checks they compose on production-shaped data.
  const recorded: MessagePart[] = [
    todo([item(A, "创建目录", "in_progress"), item(B, "写入 a.txt"), item("c", "写入 b.txt"), item("d", "列出目录内容")]),
    tool("bash", { input: { command: "ls -ld /tmp && mkdir -p /tmp/live-demo" } }),
    todo([item(A, "创建目录", "completed"), item(B, "写入 a.txt", "in_progress"), item("c", "写入 b.txt"), item("d", "列出目录内容")]),
    tool("write", { input: { file_path: "/tmp/live-demo/a.txt" } }),
    todo([item(A, "创建目录", "completed"), item(B, "写入 a.txt", "completed"), item("c", "写入 b.txt", "in_progress"), item("d", "列出目录内容")]),
    tool("write", { input: { file_path: "/tmp/live-demo/b.txt" } }),
    todo([item(A, "创建目录", "completed"), item(B, "写入 a.txt", "completed"), item("c", "写入 b.txt", "completed"), item("d", "列出目录内容", "in_progress")]),
    tool("bash", { input: { command: "ls -la /tmp/live-demo" } }),
    tool("glob", {}),
    todo([item(A, "创建目录", "completed"), item(B, "写入 a.txt", "completed"), item("c", "写入 b.txt", "completed"), item("d", "列出目录内容", "completed")]),
  ]

  it("files every call under the task it was made for", () => {
    const view = buildTurnView(recorded)
    expect(view.todo!.tasks.map((t) => t.tools.map((p) => (p as ToolPart).tool))).toEqual([
      ["bash"],
      ["write"],
      ["write"],
      ["bash", "glob"],
    ])
  })

  it("leaves nothing stranded outside the card", () => {
    const view = buildTurnView(recorded)
    expect(view.todo!.before).toEqual([])
    expect(view.todo!.after).toEqual([])
    expect(view.tools).toEqual([])
  })

  it("reads as finished", () => {
    const view = buildTurnView(recorded)
    expect([view.todo!.done, view.todo!.total, view.todo!.allDone]).toEqual([4, 4, true])
  })
})
