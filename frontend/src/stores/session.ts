import { create } from "zustand"
import { api } from "@/services/api"
import type {
  Session, SessionStatus, MessageWithParts, MessagePart, ToolStatus, TokenUsage,
} from "@/types"

const MOCK_PREFIX = "mock-"
const createSessionInflight = new Map<string, Promise<string>>()

function resolveMappedId(id: string, remap: Record<string, string>): string {
  let current = id
  const seen = new Set<string>()
  while (remap[current] && !seen.has(current)) {
    seen.add(current)
    current = remap[current]
  }
  return current
}

function mergeMessages(existing: MessageWithParts[], incoming: MessageWithParts[]): MessageWithParts[] {
  if (incoming.length === 0) return existing
  const out = [...existing]
  const ids = new Set(existing.map((m) => m.id))
  for (const msg of incoming) {
    if (!ids.has(msg.id)) {
      out.push(msg)
      ids.add(msg.id)
    }
  }
  return out
}

interface SessionStore {
  sessions: Session[]
  currentSessionId: string | null
  messages: Map<string, MessageWithParts[]>
  sessionIdRemap: Record<string, string>
  todoVersion: number
  diffVersion: number
  planVersion: number
  reset: () => void

  // Session actions
  setSessions: (sessions: Session[]) => void
  addSession: (session: Session) => void
  removeSession: (id: string) => void
  updateSessionTitle: (id: string, title: string) => void
  updateSessionStatus: (id: string, status: SessionStatus) => void
  updateSessionAgent: (id: string, agent: string) => void
  updateSessionTokens: (id: string, tokenUsage: TokenUsage) => void
  switchSession: (id: string | null) => void
  isMockSessionId: (id: string) => boolean
  resolveSessionId: (id: string) => string
  registerSessionIdRemap: (mockId: string, realId: string, realSession?: Session) => void
  ensureRealSession: (candidateId?: string | null, options?: { model?: string; agent?: string }) => Promise<string>

  // Message actions
  setMessages: (sessionId: string, messages: MessageWithParts[]) => void
  addMessage: (sessionId: string, message: MessageWithParts) => void
  updateMessage: (sessionId: string, message: MessageWithParts) => void
  appendTextDelta: (sessionId: string, messageId: string, partId: string, text: string) => void
  addPart: (sessionId: string, messageId: string, part: MessagePart) => void
  updatePart: (sessionId: string, messageId: string, part: MessagePart) => void
  appendPartDelta: (sessionId: string, messageId: string, partId: string, delta: string) => void
  updateToolStatus: (sessionId: string, partId: string, status: ToolStatus, data?: Record<string, unknown>) => void

  // Notification triggers
  notifyTodoUpdated: (sessionId: string) => void
  notifyDiffUpdated: (sessionId: string) => void
  notifyPlanUpdated: (sessionId: string) => void
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: new Map(),
  sessionIdRemap: {},
  todoVersion: 0,
  diffVersion: 0,
  planVersion: 0,
  reset: () => {
    createSessionInflight.clear()
    set({
      sessions: [],
      currentSessionId: null,
      messages: new Map(),
      sessionIdRemap: {},
      todoVersion: 0,
      diffVersion: 0,
      planVersion: 0,
    })
  },

  setSessions: (sessions) => set({ sessions }),
  addSession: (session) => set((s) => {
    const idx = s.sessions.findIndex((x) => x.id === session.id)
    if (idx >= 0) {
      const next = [...s.sessions]
      next[idx] = { ...next[idx], ...session }
      return { sessions: next }
    }
    return { sessions: [session, ...s.sessions] }
  }),
  removeSession: (id) => set((s) => ({
    sessions: s.sessions.filter((x) => x.id !== id),
    currentSessionId: s.currentSessionId === id ? null : s.currentSessionId,
  })),
  updateSessionTitle: (id, title) => set((s) => ({
    sessions: s.sessions.map((x) => (x.id === id ? { ...x, title } : x)),
  })),
  updateSessionStatus: (id, status) => set((s) => ({
    sessions: s.sessions.map((x) => (x.id === id ? { ...x, status } : x)),
  })),
  updateSessionAgent: (id, agent) => set((s) => ({
    sessions: s.sessions.map((x) => (x.id === id ? { ...x, agent } : x)),
  })),
  updateSessionTokens: (id, tokenUsage) => set((s) => ({
    sessions: s.sessions.map((x) => (x.id === id ? { ...x, token_usage: tokenUsage } : x)),
  })),
  switchSession: (id) => set({ currentSessionId: id }),

  isMockSessionId: (id) => id.startsWith(MOCK_PREFIX),
  resolveSessionId: (id) => resolveMappedId(id, get().sessionIdRemap),

  registerSessionIdRemap: (mockId, realId, realSession) => set((s) => {
    if (!mockId.startsWith(MOCK_PREFIX)) return s

    const resolvedRealId = resolveMappedId(realId, s.sessionIdRemap)
    const remap = { ...s.sessionIdRemap, [mockId]: resolvedRealId }
    for (const key of Object.keys(remap)) {
      if (remap[key] === mockId) remap[key] = resolvedRealId
    }

    const hasRealSession = s.sessions.some((x) => x.id === resolvedRealId)
    const hasMockSession = s.sessions.some((x) => x.id === mockId)

    let sessions = s.sessions
    if (hasMockSession && hasRealSession) {
      sessions = sessions.filter((x) => x.id !== mockId)
    } else if (hasMockSession) {
      sessions = sessions.map((x) => (x.id === mockId ? { ...x, id: resolvedRealId } : x))
    }

    if (realSession) {
      if (sessions.some((x) => x.id === resolvedRealId)) {
        sessions = sessions.map((x) => (x.id === resolvedRealId ? { ...x, ...realSession, id: resolvedRealId } : x))
      } else {
        sessions = [realSession, ...sessions]
      }
    }

    const messages = new Map(s.messages)
    const mockMessages = messages.get(mockId)
    if (mockMessages) {
      const normalizedMockMessages = mockMessages.map((m) => ({ ...m, session_id: resolvedRealId }))
      const realMessages = messages.get(resolvedRealId) || []
      messages.set(resolvedRealId, mergeMessages(realMessages, normalizedMockMessages))
      messages.delete(mockId)
    }

    return {
      sessionIdRemap: remap,
      sessions,
      messages,
      currentSessionId: s.currentSessionId === mockId ? resolvedRealId : s.currentSessionId,
    }
  }),

  ensureRealSession: async (candidateId, options) => {
    const current = get()
    const resolvedCandidate = candidateId ? resolveMappedId(candidateId, current.sessionIdRemap) : null
    if (resolvedCandidate && !resolvedCandidate.startsWith(MOCK_PREFIX)) {
      return resolvedCandidate
    }

    const key = resolvedCandidate || "__new__"
    const inFlight = createSessionInflight.get(key)
    if (inFlight) return inFlight

    const promise = (async () => {
      const latest = get()
      const latestCandidate = candidateId ? resolveMappedId(candidateId, latest.sessionIdRemap) : null
      if (latestCandidate && !latestCandidate.startsWith(MOCK_PREFIX)) {
        return latestCandidate
      }

      const mockSession = latestCandidate
        ? latest.sessions.find((x) => x.id === latestCandidate)
        : undefined

      const createOpts = {
        model: options?.model ?? mockSession?.model,
        agent: options?.agent ?? mockSession?.agent,
      }
      const payload = createOpts.model || createOpts.agent ? createOpts : undefined
      const session = await api.createSession(payload)

      if (latestCandidate && latestCandidate.startsWith(MOCK_PREFIX)) {
        get().registerSessionIdRemap(latestCandidate, session.id, session)
        set((s) => ({ currentSessionId: s.currentSessionId === latestCandidate ? session.id : s.currentSessionId }))
      } else {
        set((s) => {
          const hasSession = s.sessions.some((x) => x.id === session.id)
          const sessions = hasSession
            ? s.sessions.map((x) => (x.id === session.id ? { ...x, ...session } : x))
            : [session, ...s.sessions]
          return { sessions, currentSessionId: session.id }
        })
      }

      return session.id
    })().finally(() => {
      createSessionInflight.delete(key)
    })

    createSessionInflight.set(key, promise)
    return promise
  },

  setMessages: (sessionId, messages) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    map.set(resolvedSessionId, messages)
    return { messages: map }
  }),
  addMessage: (sessionId, message) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    // Deduplicate: skip if message with same ID already exists
    if (list.some((m) => m.id === message.id)) return s
    // Replace optimistic temp user message when server echo arrives.
    if (message.role === "user" && message.client_message_id) {
      const idx = list.findIndex((m) => m.id.startsWith("tmp-") && m.client_message_id === message.client_message_id)
      if (idx >= 0) {
        const next = [...list]
        next[idx] = message
        map.set(resolvedSessionId, next)
        return { messages: map }
      }
    }
    map.set(resolvedSessionId, [...list, message])
    return { messages: map }
  }),
  updateMessage: (sessionId, message) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => (m.id === message.id ? { ...m, ...message } : m)))
    return { messages: map }
  }),
  appendTextDelta: (sessionId, messageId, partId, text) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => {
      if (m.id !== messageId) return m
      return {
        ...m,
        parts: m.parts.map((p) => {
          if (p.id !== partId) return p
          if (p.type === "text") return { ...p, text: p.text + text }
          return p
        }),
      }
    }))
    return { messages: map }
  }),
  addPart: (sessionId, messageId, part) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => {
      if (m.id !== messageId) return m
      // Deduplicate: skip if part with same ID already exists
      if (m.parts.some((p) => p.id === part.id)) return m
      return { ...m, parts: [...m.parts, part] }
    }))
    return { messages: map }
  }),
  updatePart: (sessionId, messageId, part) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => {
      if (m.id !== messageId) return m
      return { ...m, parts: m.parts.map((p) => (p.id === part.id ? part : p)) }
    }))
    return { messages: map }
  }),
  appendPartDelta: (sessionId, messageId, partId, delta) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => {
      if (m.id !== messageId) return m
      return {
        ...m,
        parts: m.parts.map((p) => {
          if (p.id !== partId) return p
          if (p.type === "text" || p.type === "reasoning") return { ...p, text: p.text + delta }
          // Tool parts: accumulate raw JSON args for live preview during LLM streaming
          if (p.type === "tool") return { ...p, _streamingArgs: ((p as any)._streamingArgs || "") + delta }
          return p
        }),
      }
    }))
    return { messages: map }
  }),
  notifyTodoUpdated: (_sessionId) => set((s) => ({ todoVersion: s.todoVersion + 1 })),
  notifyDiffUpdated: (_sessionId) => set((s) => ({ diffVersion: s.diffVersion + 1 })),
  notifyPlanUpdated: (_sessionId) => set((s) => ({ planVersion: s.planVersion + 1 })),
  updateToolStatus: (sessionId, partId, status, data) => set((s) => {
    const resolvedSessionId = resolveMappedId(sessionId, s.sessionIdRemap)
    const map = new Map(s.messages)
    const list = map.get(resolvedSessionId) || []
    map.set(resolvedSessionId, list.map((m) => {
      const hasTarget = m.parts.some((p) => p.id === partId && p.type === "tool")
      if (!hasTarget) return m
      return {
        ...m,
        parts: m.parts.map((p) => {
          if (p.id !== partId || p.type !== "tool") return p
          return { ...p, status, ...data }
        }),
      }
    }))
    return { messages: map }
  }),
}))
