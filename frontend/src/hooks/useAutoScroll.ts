import { useEffect, useRef, useCallback, useState } from "react"

export function useAutoScroll<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const isAtBottomRef = useRef(true)

  const checkAtBottom = useCallback(() => {
    const el = ref.current
    if (!el) return
    const threshold = 50
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    isAtBottomRef.current = atBottom
    setIsAtBottom((prev) => (prev === atBottom ? prev : atBottom))
  }, [])

  const scrollToBottom = useCallback(() => {
    const el = ref.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" })
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new MutationObserver(() => {
      if (isAtBottomRef.current) {
        el.scrollTo({ top: el.scrollHeight })
      }
    })

    observer.observe(el, { childList: true, subtree: true })
    el.addEventListener("scroll", checkAtBottom)

    return () => {
      observer.disconnect()
      el.removeEventListener("scroll", checkAtBottom)
    }
  }, [checkAtBottom])

  return { ref, isAtBottom, scrollToBottom }
}
