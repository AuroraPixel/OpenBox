import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { ArrowDown } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import type { Turn } from "../lib/turn-view"
import { AssistantTurn, TypingRow } from "./AssistantTurn"
import { UserBubble } from "./UserBubble"

const VIRTUAL_THRESHOLD = 50

interface Row {
  key: string
  node: ReactNode
}

/** Virtualized row list — only mounted for long histories (> 50 rows). */
function VirtualRows({ rows, scrollRef }: { rows: Row[]; scrollRef: RefObject<HTMLDivElement | null> }) {
  // eslint-disable-next-line react-hooks/incompatible-library -- tanstack virtual is the project's chosen virtualizer
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 260,
    overscan: 8,
  })
  return (
    <div style={{ position: "relative", width: "100%", height: virtualizer.getTotalSize() }}>
      {virtualizer.getVirtualItems().map((item) => (
        <div
          key={rows[item.index].key}
          data-index={item.index}
          ref={virtualizer.measureElement}
          className="flex flex-col pb-6"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            transform: `translateY(${item.start}px)`,
          }}
        >
          {rows[item.index].node}
        </div>
      ))}
    </div>
  )
}

interface Props {
  turns: Turn[]
  sessionId: string
  busy: boolean
  /** Pending cards / plan card rendered below the last turn, inside the scroll area. */
  footer?: ReactNode
}

/** Scrolling message column: centered, auto-sticks to the bottom, back-to-bottom fab. */
export function ChatFlow({ turns, sessionId, busy, footer }: Props) {
  const { t } = useTranslation("chat")
  const scrollRef = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)

  const rows = useMemo<Row[]>(() => {
    const list: Row[] = turns.map((turn, i) => ({
      key: turn.key,
      node:
        turn.kind === "user" ? (
          <UserBubble message={turn.message} />
        ) : (
          <AssistantTurn
            parts={turn.parts}
            meta={turn.meta}
            sessionId={sessionId}
            streaming={busy && i === turns.length - 1}
          />
        ),
    }))
    if (busy && turns.length > 0 && turns[turns.length - 1].kind === "user") {
      list.push({ key: "typing", node: <TypingRow /> })
    }
    return list
  }, [turns, sessionId, busy])

  const atBottomRef = useRef(true)
  const onScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const at = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    atBottomRef.current = at
    setAtBottom(at)
  }, [])

  // Stick to the bottom as content grows. Streaming changes content height
  // between React commits (streamdown animates blocks in), so follow real
  // element growth with a ResizeObserver rather than render passes.
  const contentRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = scrollRef.current
    const content = contentRef.current
    if (!el || !content) return
    const ro = new ResizeObserver(() => {
      if (atBottomRef.current) el.scrollTop = el.scrollHeight
    })
    ro.observe(content)
    return () => ro.disconnect()
  }, [])
  useEffect(() => {
    const el = scrollRef.current
    if (el && atBottomRef.current) el.scrollTop = el.scrollHeight
  }, [rows, footer])

  // Sending your own message always jumps to the bottom, wherever you were.
  const lastUserKey = [...turns].reverse().find((tn) => tn.kind === "user")?.key
  const prevUserKey = useRef(lastUserKey)
  useEffect(() => {
    if (lastUserKey !== prevUserKey.current) {
      prevUserKey.current = lastUserKey
      const el = scrollRef.current
      if (el) {
        atBottomRef.current = true
        setAtBottom(true)
        el.scrollTop = el.scrollHeight
      }
    }
  }, [lastUserKey])

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  const virtual = rows.length > VIRTUAL_THRESHOLD

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="scr h-full overflow-y-auto overscroll-contain px-6.5 pt-1.5 pb-2 [overflow-anchor:none]"
      >
        <div ref={contentRef} className="mx-auto flex w-full max-w-190 flex-col gap-6 pb-4">
          {virtual ? (
            <VirtualRows rows={rows} scrollRef={scrollRef} />
          ) : (
            rows.map((r) => (
              <div key={r.key} className="flex flex-col">
                {r.node}
              </div>
            ))
          )}
          {footer}
        </div>
      </div>
      <div
        aria-hidden
        className="from-bg pointer-events-none absolute inset-x-0 top-0 h-8 bg-gradient-to-b to-transparent"
      />
      <div
        aria-hidden
        className={cn(
          "from-bg pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t to-transparent transition-opacity duration-150",
          atBottom ? "opacity-0" : "opacity-100",
        )}
      />
      {!atBottom && (
        <button
          type="button"
          onClick={scrollToBottom}
          aria-label={t("scrollBottom")}
          className="border-hair bg-card shadow-pop absolute start-1/2 bottom-4 -translate-x-1/2 rounded-full border p-2"
        >
          <ArrowDown className="text-n700 size-4" />
        </button>
      )}
    </div>
  )
}
