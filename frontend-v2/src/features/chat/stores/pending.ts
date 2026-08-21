// Pending permission & question requests, keyed by session. Seeded from the
// list queries on mount / reconnect, kept live by the WS bridge.
import { create } from "zustand"
import type { PermissionRequest, QuestionRequest } from "@/shared/types/api"

type PermMap = Map<string, PermissionRequest[]>
type QsMap = Map<string, QuestionRequest[]>

interface PendingState {
  permissions: PermMap
  questions: QsMap
  setPermissions: (items: PermissionRequest[]) => void
  addPermission: (item: PermissionRequest) => void
  removePermission: (requestId: string) => void
  setQuestions: (items: QuestionRequest[]) => void
  addQuestion: (item: QuestionRequest) => void
  removeQuestion: (requestId: string) => void
}

function groupBySession<T extends { session_id: string }>(items: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>()
  for (const item of items) {
    const list = map.get(item.session_id) ?? []
    list.push(item)
    map.set(item.session_id, list)
  }
  return map
}

function add<T extends { id: string; session_id: string }>(
  prev: Map<string, T[]>,
  item: T,
): Map<string, T[]> {
  const map = new Map(prev)
  const list = map.get(item.session_id) ?? []
  if (list.some((x) => x.id === item.id)) return prev
  map.set(item.session_id, [...list, item])
  return map
}

function remove<T extends { id: string }>(prev: Map<string, T[]>, requestId: string): Map<string, T[]> {
  const map = new Map<string, T[]>()
  let changed = false
  for (const [sid, list] of prev) {
    const next = list.filter((x) => x.id !== requestId)
    if (next.length !== list.length) changed = true
    map.set(sid, next)
  }
  return changed ? map : prev
}

export const usePendingStore = create<PendingState>((set) => ({
  permissions: new Map(),
  questions: new Map(),
  setPermissions: (items) => set({ permissions: groupBySession(items) }),
  addPermission: (item) => set((s) => ({ permissions: add(s.permissions, item) })),
  removePermission: (requestId) => set((s) => ({ permissions: remove(s.permissions, requestId) })),
  setQuestions: (items) => set({ questions: groupBySession(items) }),
  addQuestion: (item) => set((s) => ({ questions: add(s.questions, item) })),
  removeQuestion: (requestId) => set((s) => ({ questions: remove(s.questions, requestId) })),
}))
