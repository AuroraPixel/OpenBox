// Streaming message store — physically isolated from TanStack Query (§7.4).
// The initial snapshot comes from useMessagesQuery (setMessages); every later
// increment arrives over the WebSocket. Server state is never re-poured in
// beyond that first merge. Ported from v1's reducer, retyped for this project.
import { create } from "zustand"
import type {
  MessagePart,
  MessageReaction,
  MessageWithParts,
  SessionStatus,
  ToolPart,
  ToolStatus,
} from "@/shared/types/api"

type MsgMap = Map<string, MessageWithParts[]>

interface StreamState {
  messages: MsgMap
  /** Live session status, fed by WS session.status + optimistic send. */
  status: Map<string, SessionStatus>
  setMessages: (sessionId: string, messages: MessageWithParts[]) => void
  addMessage: (sessionId: string, message: MessageWithParts) => void
  updateMessage: (sessionId: string, message: MessageWithParts) => void
  appendPartDelta: (sessionId: string, messageId: string, partId: string, delta: string) => void
  addPart: (sessionId: string, messageId: string, part: MessagePart) => void
  updatePart: (sessionId: string, messageId: string, part: MessagePart) => void
  updateToolStatus: (
    sessionId: string,
    partId: string,
    status: ToolStatus,
    data?: Record<string, unknown>,
  ) => void
  setStatus: (sessionId: string, status: SessionStatus) => void
  /** Optimistic thumbs up/down for one message (server echo follows). */
  setMessageReaction: (sessionId: string, messageId: string, reaction: MessageReaction) => void
}

function commit(prev: MsgMap, sessionId: string, next: MessageWithParts[]): { messages: MsgMap } {
  const map = new Map(prev)
  map.set(sessionId, next)
  return { messages: map }
}

function mapParts(
  list: MessageWithParts[],
  messageId: string,
  fn: (parts: MessagePart[]) => MessagePart[],
): MessageWithParts[] {
  return list.map((m) => (m.id === messageId ? { ...m, parts: fn(m.parts) } : m))
}

/** Narrow a loose WS tool payload into a typed patch (no `any`). */
function toolPatch(status: ToolStatus, data?: Record<string, unknown>): Partial<ToolPart> {
  const patch: Partial<ToolPart> = { status }
  if (data) {
    if (typeof data.output === "string") patch.output = data.output
    if (typeof data.error === "string") patch.error = data.error
    if (typeof data.duration === "number") patch.duration = data.duration
    if (typeof data.title === "string") patch.title = data.title
    if (data.input && typeof data.input === "object") patch.input = data.input as Record<string, unknown>
  }
  return patch
}

export const useStreamStore = create<StreamState>((set) => ({
  messages: new Map(),
  status: new Map(),

  // Merge-union: keeps optimistic/streamed-ahead messages and the longer parts
  // list so a late snapshot refetch (e.g. after reconnect) never clobbers live
  // state, while an empty store is simply seeded with the snapshot.
  setMessages: (sessionId, incoming) =>
    set((s) => {
      const existing = s.messages.get(sessionId) ?? []
      if (existing.length === 0) return commit(s.messages, sessionId, incoming)
      const incomingIds = new Set(incoming.map((m) => m.id))
      const incomingCids = new Set(incoming.map((m) => m.client_message_id).filter(Boolean))
      const merged = incoming.map((im) => {
        const ex = existing.find((e) => e.id === im.id)
        return ex && ex.parts.length >= im.parts.length ? ex : im
      })
      const extras = existing.filter(
        (e) => !incomingIds.has(e.id) && !(e.client_message_id && incomingCids.has(e.client_message_id)),
      )
      return commit(s.messages, sessionId, [...merged, ...extras])
    }),

  addMessage: (sessionId, message) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      if (list.some((m) => m.id === message.id)) return s
      // Replace the optimistic temp message once the server echo arrives.
      if (message.client_message_id) {
        const idx = list.findIndex(
          (m) => m.id.startsWith("tmp-") && m.client_message_id === message.client_message_id,
        )
        if (idx >= 0) {
          const next = [...list]
          next[idx] = message
          return commit(s.messages, sessionId, next)
        }
      }
      return commit(s.messages, sessionId, [...list, message])
    }),

  updateMessage: (sessionId, message) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      return commit(
        s.messages,
        sessionId,
        list.map((m) => (m.id === message.id ? { ...m, ...message } : m)),
      )
    }),

  appendPartDelta: (sessionId, messageId, partId, delta) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      return commit(
        s.messages,
        sessionId,
        mapParts(list, messageId, (parts) =>
          parts.map((p) =>
            p.id === partId && (p.type === "text" || p.type === "reasoning")
              ? { ...p, text: p.text + delta }
              : p,
          ),
        ),
      )
    }),

  addPart: (sessionId, messageId, part) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      return commit(
        s.messages,
        sessionId,
        mapParts(list, messageId, (parts) =>
          parts.some((p) => p.id === part.id) ? parts : [...parts, part],
        ),
      )
    }),

  updatePart: (sessionId, messageId, part) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      return commit(
        s.messages,
        sessionId,
        mapParts(list, messageId, (parts) => parts.map((p) => (p.id === part.id ? part : p))),
      )
    }),

  updateToolStatus: (sessionId, partId, status, data) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      const patch = toolPatch(status, data)
      return commit(
        s.messages,
        sessionId,
        list.map((m) =>
          m.parts.some((p) => p.id === partId && p.type === "tool")
            ? {
                ...m,
                parts: m.parts.map((p) => (p.id === partId && p.type === "tool" ? { ...p, ...patch } : p)),
              }
            : m,
        ),
      )
    }),

  setStatus: (sessionId, status) =>
    set((s) => {
      const map = new Map(s.status)
      map.set(sessionId, status)
      return { status: map }
    }),

  setMessageReaction: (sessionId, messageId, reaction) =>
    set((s) => {
      const list = s.messages.get(sessionId) ?? []
      return commit(
        s.messages,
        sessionId,
        list.map((m) => (m.id === messageId ? { ...m, reaction } : m)),
      )
    }),
}))

const BUSY: ReadonlySet<SessionStatus> = new Set<SessionStatus>(["busy", "finalizing", "retry", "compacting"])

export function isBusyStatus(status: SessionStatus | undefined): boolean {
  return status !== undefined && BUSY.has(status)
}
