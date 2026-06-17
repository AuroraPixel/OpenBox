import { create } from "zustand"
import type { QuestionRequest } from "@/types"

interface QuestionStore {
  pending: QuestionRequest[]
  addPending: (req: QuestionRequest) => void
  removePending: (id: string) => void
  clearAll: () => void
}

export const useQuestionStore = create<QuestionStore>((set) => ({
  pending: [],
  addPending: (req) => set((s) => ({
    pending: s.pending.some((q) => q.id === req.id) ? s.pending : [...s.pending, req],
  })),
  removePending: (id) => set((s) => ({ pending: s.pending.filter((q) => q.id !== id) })),
  clearAll: () => set({ pending: [] }),
}))
