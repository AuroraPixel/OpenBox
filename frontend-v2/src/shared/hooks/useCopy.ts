import { useCallback, useRef, useState } from "react"

/** Clipboard copy with a short "copied" flash. */
export function useCopy(resetMs = 1600) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | null>(null)
  const copy = useCallback(
    (text: string) => {
      void navigator.clipboard.writeText(text).then(() => {
        setCopied(true)
        if (timer.current !== null) window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => setCopied(false), resetMs)
      })
    },
    [resetMs],
  )
  return { copied, copy }
}
