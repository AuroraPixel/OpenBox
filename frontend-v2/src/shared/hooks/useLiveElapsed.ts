import { useEffect, useState } from "react"

/**
 * Milliseconds elapsed since `startIso`, refreshed every 500ms while `enabled`.
 * Returns 0 (and starts no timer) when disabled or the timestamp is unusable.
 * The clock is read only inside timer callbacks, never during render.
 */
export function useLiveElapsed(startIso: string | undefined, enabled: boolean): number {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!enabled || !startIso) return
    const start = new Date(startIso).getTime()
    if (Number.isNaN(start)) return
    const update = () => setElapsed(Math.max(0, Date.now() - start))
    // Kick off on the next tick so the first value isn't set synchronously
    // inside the effect body, then keep it live on an interval.
    const kickoff = window.setTimeout(update, 0)
    const id = window.setInterval(update, 500)
    return () => {
      window.clearTimeout(kickoff)
      window.clearInterval(id)
    }
  }, [startIso, enabled])

  return enabled ? elapsed : 0
}
