// Which model the composer sends with.
//
// A conversation carries its own model: the backend records the choice on the
// session, so reopening one restores what it was last using instead of the
// global default. An unsent pick belongs to the chat it was made in, so moving
// to another conversation clears it rather than carrying it across.
import { useState } from "react"

interface Options {
  /** The model this conversation last used, from the session record. */
  sessionModel?: string
  /** Changes when the user moves to another conversation. */
  sessionKey?: string
  /** Deployment default, for a conversation that has not chosen yet. */
  fallback?: string
}

export function useModelChoice({ sessionModel, sessionKey, fallback }: Options) {
  const [picked, setPicked] = useState<string | undefined>(undefined)
  const [pickedFor, setPickedFor] = useState(sessionKey)

  if (pickedFor !== sessionKey) {
    setPickedFor(sessionKey)
    setPicked(undefined)
  }

  return { activeId: picked ?? sessionModel ?? fallback, pick: setPicked }
}
