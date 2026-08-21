// The model the user has selected in the composer but not yet sent with.
//
// This lives in a store rather than in the composer's own state because two
// distant places need the same answer: the picker that sets it, and the retry
// button on a failed turn. "This model is down, try another one" is the most
// common reason anyone regenerates, so a retry that silently reuses the model
// that just failed is a button that does nothing.
//
// Keyed by session: an unsent choice belongs to the conversation it was made
// in, and switching chats must not carry it along.
import { create } from "zustand"

interface ModelChoiceState {
  picked: Map<string, string>
  pick: (sessionKey: string, modelId: string) => void
  /** Drop the pick for one conversation (it has been sent, or abandoned). */
  clear: (sessionKey: string) => void
}

export const useModelChoiceStore = create<ModelChoiceState>((set) => ({
  picked: new Map(),
  pick: (sessionKey, modelId) =>
    set((s) => {
      const next = new Map(s.picked)
      next.set(sessionKey, modelId)
      return { picked: next }
    }),
  clear: (sessionKey) =>
    set((s) => {
      if (!s.picked.has(sessionKey)) return s
      const next = new Map(s.picked)
      next.delete(sessionKey)
      return { picked: next }
    }),
}))

/** The unsent model choice for a conversation, if the user made one.
 *
 *  Deliberately returns `undefined` rather than a default: callers pass it
 *  straight to the API, where absent means "keep whatever the session already
 *  runs on". Substituting a default here would silently pin every retry.
 */
export function usePickedModel(sessionKey: string | undefined): string | undefined {
  return useModelChoiceStore((s) => (sessionKey ? s.picked.get(sessionKey) : undefined))
}
