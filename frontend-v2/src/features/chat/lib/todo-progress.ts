// How full the bar under a running task is.
//
// There is no honest number to show here: the model does not say how much of
// a task is left, and it may run one command or twenty. So the bar is a
// fiction — but a *deterministic* one, computed from when the task started
// and how much it has done, never from a timer inside the component.
//
// That matters more than it sounds. A timer-driven bar restarts at zero on
// every reload and disagrees between two tabs watching the same run. This one
// is a pure function of data that is already persisted, so a reload picks the
// bar up exactly where it was.

/** Never reaches the top: a full bar on an unfinished task reads as a stall. */
const CEILING = 0.9
/** Where the bar sits the moment a task starts, so it is visible at once. */
const FLOOR = 0.06
/** Seconds for the time-based half to run its course. */
const PACE = 90
/** Each finished call is worth this much, up to `STEP_MAX`. */
const STEP_WEIGHT = 0.08
const STEP_MAX = 0.45

export interface ProgressInput {
  /** ISO time the task became in_progress; null before it starts. */
  startedAt?: string | null
  /** Calls this task has finished. */
  steps: number
  /** Now, in ms — passed in so the value is reproducible under test. */
  now: number
}

/** Fraction filled, 0…1. A completed task is 1; nothing else ever is. */
export function taskProgress({ startedAt, steps, now }: ProgressInput): number {
  if (!startedAt) return 0
  const began = Date.parse(startedAt)
  if (Number.isNaN(began)) return FLOOR
  const elapsed = Math.max(0, (now - began) / 1000)

  // Asymptotic in elapsed time: quick at first, then slower, never arriving.
  // Work done pushes it along faster than waiting does, so a task making
  // calls visibly outpaces one that is stuck on a single slow command.
  const byTime = 1 - Math.exp(-elapsed / PACE)
  const byWork = Math.min(STEP_MAX, steps * STEP_WEIGHT)
  const combined = FLOOR + (CEILING - FLOOR) * (byTime * 0.6 + byWork / STEP_MAX * 0.4)
  return Math.min(CEILING, combined)
}

/** The bar as a percentage, for display. */
export function progressPercent(value: number): number {
  return Math.round(value * 100)
}
