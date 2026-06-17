import { create } from "zustand"
import type { PermissionRequest } from "@/types"

interface PermissionStore {
  pending: PermissionRequest[]
  addPending: (req: PermissionRequest) => void
  removePending: (id: string) => void
  clearAll: () => void
}

export const usePermissionStore = create<PermissionStore>((set) => ({
  pending: [],
  addPending: (req) => set((s) => ({
    pending: s.pending.some((p) => p.id === req.id) ? s.pending : [...s.pending, req],
  })),
  removePending: (id) => set((s) => ({ pending: s.pending.filter((p) => p.id !== id) })),
  clearAll: () => set({ pending: [] }),
}))
