import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { MessageBubble } from "./MessageBubble"
import { ArrowDown, MessageSquare } from "lucide-react"
import type { MessageWithParts } from "@/types"

interface MessageListProps {
  messages: MessageWithParts[]
  sessionId: string
  isBusy?: boolean
}

export function MessageList({ messages, sessionId, isBusy }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)

  // Merge consecutive assistant messages that share the same parent_id (same turn)
  const mergedMessages = useMemo(() => {
    const result: MessageWithParts[] = []
    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i]
      if (
        msg.role === "assistant" &&
        msg.parent_id &&
        result.length > 0 &&
        result[result.length - 1].role === "assistant" &&
        result[result.length - 1].parent_id === msg.parent_id
      ) {
        // Merge into the previous message: combine parts
        const prev = result[result.length - 1]
        result[result.length - 1] = {
          ...prev,
          parts: [...prev.parts, ...msg.parts],
          // Keep the latest model/agent info
          model: msg.model || prev.model,
          agent: msg.agent || prev.agent,
          // Track all original message IDs for store operations
          _mergedIds: [...((prev as any)._mergedIds || [prev.id]), msg.id],
        } as MessageWithParts
      } else {
        result.push(msg)
      }
    }
    return result
  }, [messages])

  const rows = useMemo(() => {
    const list: Array<{ kind: "message"; msg: MessageWithParts } | { kind: "typing" }> = mergedMessages.map((msg) => ({
      kind: "message",
      msg,
    }))
    if (isBusy && messages.length > 0 && messages[messages.length - 1].role === "user") {
      list.push({ kind: "typing" })
    }
    return list
  }, [mergedMessages, messages, isBusy])

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (index) => (rows[index]?.kind === "typing" ? 44 : 220),
    overscan: 8,
  })

  const checkAtBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const threshold = 50
    setIsAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < threshold)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.addEventListener("scroll", checkAtBottom)
    checkAtBottom()
    return () => el.removeEventListener("scroll", checkAtBottom)
  }, [checkAtBottom])

  useEffect(() => {
    if (!isAtBottom || rows.length === 0) return
    virtualizer.scrollToIndex(rows.length - 1, { align: "end" })
  }, [isAtBottom, rows.length, virtualizer])

  const scrollToBottom = useCallback(() => {
    if (rows.length === 0) return
    virtualizer.scrollToIndex(rows.length - 1, { align: "end" })
  }, [rows.length, virtualizer])

  if (messages.length === 0) {
    return (
      <div className="h-full flex items-center justify-center grid-pattern">
        <div className="text-center max-w-md">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 mb-4 shadow-[0_0_12px_hsl(var(--primary)/0.2)]">
            <MessageSquare className="h-6 w-6 text-[hsl(var(--primary))] glow-cyan" />
          </div>
          <h3 className="text-base font-display font-medium mb-1 text-[hsl(var(--foreground))]">Start a conversation</h3>
          <p className="text-sm text-[hsl(var(--muted-foreground))] font-mono">
            Send a message to begin working with the AI agent
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full relative">
      <div ref={scrollRef} className="h-full overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-6">
          <div style={{ height: `${virtualizer.getTotalSize()}px`, width: "100%", position: "relative" }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = rows[item.index]
              if (!row) return null
              return (
                <div
                  key={item.key}
                  ref={virtualizer.measureElement}
                  data-index={item.index}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${item.start}px)`,
                    paddingBottom: "1.5rem",
                  }}
                >
                  {row.kind === "message" ? (
                    <MessageBubble
                      message={row.msg}
                      sessionId={sessionId}
                      isBusy={isBusy}
                      isLastMessage={item.index === mergedMessages.length - 1}
                    />
                  ) : (
                    <div className="flex items-center gap-3 py-3 pl-10">
                      <div className="flex items-center gap-1.5">
                        <div className="h-1.5 w-1.5 rounded-sm bg-[hsl(var(--primary))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--primary))]" />
                        <div className="h-1.5 w-1.5 rounded-sm bg-[hsl(var(--primary))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--primary))]" style={{ animationDelay: "0.15s" }} />
                        <div className="h-1.5 w-1.5 rounded-sm bg-[hsl(var(--primary))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--primary))]" style={{ animationDelay: "0.3s" }} />
                      </div>
                      <span className="text-sm text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider animate-flicker">Thinking...</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      {!isAtBottom && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3.5 py-2 rounded-sm bg-[hsl(var(--card))] border border-[hsl(var(--primary))]/20 shadow-[0_0_10px_hsl(var(--primary)/0.15)] hover:shadow-[0_0_16px_hsl(var(--primary)/0.25)] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer text-xs text-[hsl(var(--primary))] font-mono uppercase tracking-wider"
          aria-label="Scroll to bottom"
        >
          <ArrowDown className="h-3 w-3" />
          New messages
        </button>
      )}
    </div>
  )
}
