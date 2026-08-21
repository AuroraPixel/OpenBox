// Which model the composer sends with.
//
// A conversation carries its own model: the backend records the choice on the
// session, so reopening one restores what it was last using instead of the
// global default. An unsent pick belongs to the chat it was made in, so moving
// to another conversation clears it rather than carrying it across.
//
// The pick itself lives in a store, not in this hook's state, because the
// retry button on a failed turn needs to read it too — see model-choice.ts.
import { useEffect } from "react"
import { useModelChoiceStore, usePickedModel } from "../stores/model-choice"

interface Options {
  /** The model this conversation last used, from the session record. */
  sessionModel?: string
  /** Changes when the user moves to another conversation. */
  sessionKey?: string
  /** Deployment default, for a conversation that has not chosen yet. */
  fallback?: string
}

export function useModelChoice({ sessionModel, sessionKey, fallback }: Options) {
  const key = sessionKey ?? ""
  const picked = usePickedModel(key)
  const pickInStore = useModelChoiceStore((s) => s.pick)
  const clear = useModelChoiceStore((s) => s.clear)

  // Leaving a conversation drops its unsent pick. Done on unmount rather than
  // by comparing keys during render, because the store is shared: a render-time
  // reset would also wipe the pick made in whichever chat mounted next.
  useEffect(() => () => clear(key), [key, clear])

  return {
    activeId: picked ?? sessionModel ?? fallback,
    pick: (id: string) => pickInStore(key, id),
  }
}
