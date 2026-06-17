import { useCallback, useState, useMemo, memo } from "react"
import { cn } from "@/lib/utils"
import { User, Bot, RotateCcw, Copy, Check } from "lucide-react"
import { TextPart } from "@/components/parts/TextPart"
import { ReasoningPart } from "@/components/parts/ReasoningPart"
import { ToolPart } from "@/components/parts/ToolPart"
import { StepDivider } from "@/components/parts/StepDivider"
import { StepSummary } from "@/components/parts/StepSummary"
import { CompactionBadge } from "@/components/parts/CompactionBadge"
import { AgentSwitchBadge } from "@/components/parts/AgentSwitchBadge"
import { RetryBadge } from "@/components/parts/RetryBadge"
import { PatchPart } from "@/components/parts/PatchPart"
import { PlanCard } from "@/components/parts/PlanCard"
import { ProcessCard } from "@/components/parts/ProcessCard"
import { StreamingStatus } from "@/components/parts/StreamingStatus"
import { api } from "@/services/api"
import { useSessionStore } from "@/stores/session"
import type { MessageWithParts, MessagePart } from "@/types"

interface MessageBubbleProps {
  message: MessageWithParts
  sessionId: string
  isBusy?: boolean
  isLastMessage?: boolean
}

export const MessageBubble = memo(function MessageBubble({ message, sessionId, isBusy, isLastMessage }: MessageBubbleProps) {
  const resolvedSessionId = useSessionStore((s) => s.resolveSessionId(sessionId))
  const [reverting, setReverting] = useState(false)
  const [reverted, setReverted] = useState(false)
  const [unreverting, setUnreverting] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    const textContent = message.parts
      .filter((p) => p.type === "text" && !(p as { synthetic?: boolean }).synthetic)
      .map((p) => (p as { text?: string }).text || "")
      .join("\n")
    navigator.clipboard.writeText(textContent).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [message.parts])

  const handleRevert = useCallback(async () => {
    if (reverting || resolvedSessionId.startsWith("mock-")) return
    setReverting(true)
    try {
      await api.revert(resolvedSessionId, message.id)
      setReverted(true)
    } catch {
      // ignore if backend not ready
    } finally {
      setReverting(false)
    }
  }, [reverting, resolvedSessionId, message.id])

  const handleUnrevert = useCallback(async () => {
    if (unreverting || resolvedSessionId.startsWith("mock-")) return
    setUnreverting(true)
    try {
      await api.unrevert(resolvedSessionId)
      setReverted(false)
    } catch {
      // ignore if backend not ready
    } finally {
      setUnreverting(false)
    }
  }, [unreverting, resolvedSessionId])
  const isUser = message.role === "user"
  const hasTextPart = message.parts.some((p) => p.type === "text" && !(p as { synthetic?: boolean }).synthetic)

  // Filter out synthetic parts and empty text in compaction messages
  const hasCompactionPart = message.parts.some((p) => p.type === "compaction")
  const visibleParts = message.parts.filter((p) => {
    // Hide synthetic text parts (system-generated reminders)
    if (p.type === "text" && (p as { synthetic?: boolean }).synthetic) return false
    // Hide empty text parts in compaction user messages (prevents white card)
    if (p.type === "text" && hasCompactionPart && !(p as { text?: string }).text?.trim()) return false
    return true
  })

  // Hide entirely synthetic user messages (e.g. plan_enter/plan_exit transitions)
  if (isUser && visibleParts.length === 0) return null

  // Compaction user messages: render only the CompactionBadge, no bubble
  if (isUser && hasCompactionPart && visibleParts.every((p) => p.type === "compaction")) {
    return (
      <div className="my-2">
        {visibleParts.map((part) => (
          <PartRenderer key={part.id} part={part} sessionId={sessionId} />
        ))}
      </div>
    )
  }

  return (
    <div className={cn("group", isUser ? "flex justify-end" : "")}>
      {isUser ? (
        /* User message: right-aligned bubble */
        <div className="flex items-start gap-2 sm:gap-2.5 max-w-[95%] sm:max-w-[80%]">
          <button
            onClick={handleCopy}
            className="opacity-0 group-hover:opacity-100 p-1 rounded-sm hover:bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-all cursor-pointer self-center shrink-0"
            aria-label="Copy message"
            title="Copy"
          >
            {copied ? <Check className="h-3 w-3 text-[hsl(var(--success))]" /> : <Copy className="h-3 w-3" />}
          </button>
          <div className="rounded-sm rounded-tr-none bg-[hsl(var(--bubble-user))] px-4 py-3 border border-[hsl(var(--border))]/30">
            <div className="space-y-2">
              {visibleParts.map((part) => (
                <PartRenderer key={part.id} part={part} sessionId={sessionId} />
              ))}
            </div>
          </div>
          <div className="w-7 h-7 rounded-sm bg-[hsl(var(--muted))] flex items-center justify-center shrink-0 mt-1 border border-[hsl(var(--border))]/30">
            <User className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]" />
          </div>
        </div>
      ) : (
        /* Assistant message: full-width */
        <div className="flex items-start gap-3">
          <div className="w-7 h-7 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 flex items-center justify-center shrink-0 mt-1 shadow-[0_0_8px_hsl(var(--primary)/0.2)]">
            <Bot className="h-3.5 w-3.5 text-[hsl(var(--primary))] glow-cyan" />
          </div>
          <div className="flex-1 min-w-0">
            {/* Agent/model tag */}
            <div className="flex items-center gap-2 mb-2 text-xs text-[hsl(var(--muted-foreground))]">
              <span className="font-display font-medium text-[hsl(var(--foreground))]">
                {message.model?.split("/").pop() || "Assistant"}
              </span>
              {message.agent && (
                <span className="px-1.5 py-0.5 rounded-sm bg-[hsl(var(--muted))] text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--accent))]">
                  {message.agent}
                </span>
              )}
              <span className="opacity-0 group-hover:opacity-100 transition-opacity tabular-nums font-mono text-[10px]">
                {new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
              <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
                <button
                  onClick={handleCopy}
                  className="p-1 rounded-sm hover:bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors cursor-pointer"
                  aria-label="Copy message"
                  title="Copy"
                >
                  {copied ? <Check className="h-3 w-3 text-[hsl(var(--success))]" /> : <Copy className="h-3 w-3" />}
                </button>
                <button
                  onClick={handleRevert}
                  disabled={reverting}
                  className="p-1 rounded-sm hover:bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors cursor-pointer disabled:opacity-50"
                  aria-label="Revert to this message"
                  title="Revert to here"
                >
                  <RotateCcw className={cn("h-3 w-3", reverting && "animate-spin")} />
                </button>
              </div>
            </div>

            {/* Parts — group process parts into collapsible ProcessCard */}
            <div className={cn(
              "space-y-3 rounded-sm rounded-tl-none px-4 py-3 border",
              message.summary
                ? "bg-[hsl(var(--primary))]/5 border-[hsl(var(--primary))]/20"
                : "bg-[hsl(var(--bubble-assistant))] border-[hsl(var(--border))]/20",
            )}>
              <GroupedParts
                parts={message.parts}
                sessionId={sessionId}
                isStreaming={!!isBusy && !!isLastMessage}
                hasTextPart={hasTextPart}
              />
            </div>

            {/* Streaming status indicator */}
            {isBusy && isLastMessage && (
              <StreamingStatus message={message} />
            )}

            {/* Undo revert banner */}
            {reverted && (
              <div className="flex items-center gap-2 mt-3 px-3 py-2 rounded-sm bg-[hsl(var(--accent))]/8 border border-[hsl(var(--accent))]/15 text-xs text-[hsl(var(--accent))] glow-amber">
                <span className="font-mono uppercase tracking-wider">Reverted to this point.</span>
                <button
                  onClick={handleUnrevert}
                  disabled={unreverting}
                  className="underline hover:no-underline cursor-pointer disabled:opacity-50 font-mono"
                >
                  {unreverting ? "Undoing..." : "Undo"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
})

// Content types that should always be visible outside the ProcessCard (final output)
const CONTENT_TYPES = new Set(["text", "plan", "patch", "file"])

function GroupedParts({ parts, sessionId, isStreaming, hasTextPart }: {
  parts: MessagePart[]
  sessionId: string
  isStreaming?: boolean
  hasTextPart?: boolean
}) {
  const { processParts, tailParts, processKey } = useMemo(() => {
    // Filter out synthetic text
    const visible = parts.filter((p) => !(p.type === "text" && (p as { synthetic?: boolean }).synthetic))

    // Find the last content part index (the final answer)
    // Everything before it → ProcessCard, everything from it onward → direct render
    let lastContentIdx = -1
    for (let i = visible.length - 1; i >= 0; i--) {
      if (CONTENT_TYPES.has(visible[i].type)) {
        lastContentIdx = i
        break
      }
    }

    let processParts: MessagePart[]
    let tailParts: MessagePart[]

    if (lastContentIdx === -1) {
      // No content parts at all — everything is process
      processParts = visible
      tailParts = []
    } else {
      // Everything before the last content part → process card
      processParts = visible.slice(0, lastContentIdx)
      // Last content part and after → always visible
      tailParts = visible.slice(lastContentIdx)
    }

    return {
      processParts,
      tailParts,
      processKey: processParts.length > 0 ? `process-${processParts[0].id}` : "",
    }
  }, [parts])

  // No process parts — render flat
  if (processParts.length === 0) {
    return (
      <>
        {tailParts.map((part) => (
          <PartRenderer key={part.id} part={part} sessionId={sessionId} isStreaming={isStreaming} hasTextPart={hasTextPart} />
        ))}
      </>
    )
  }

  return (
    <>
      <ProcessCard
        key={processKey}
        parts={processParts}
        isStreaming={isStreaming && tailParts.length === 0}
        renderPart={(part) => (
          <PartRenderer part={part} sessionId={sessionId} isStreaming={isStreaming} hasTextPart={hasTextPart} />
        )}
      />
      {tailParts.map((part) => (
        <PartRenderer key={part.id} part={part} sessionId={sessionId} isStreaming={isStreaming} hasTextPart={hasTextPart} />
      ))}
    </>
  )
}

function PartRenderer({ part, sessionId, isStreaming, hasTextPart }: { part: MessagePart; sessionId: string; isStreaming?: boolean; hasTextPart?: boolean }) {
  switch (part.type) {
    case "text":
      return <TextPart text={part.text} isStreaming={isStreaming} />
    case "reasoning":
      return <ReasoningPart text={part.text} isStreaming={isStreaming && !hasTextPart} />
    case "tool":
      return <ToolPart part={part} />
    case "step-start":
      return <StepDivider step={part.step} />
    case "step-finish":
      return <StepSummary inputTokens={part.input_tokens} outputTokens={part.output_tokens} cost={part.cost} duration={part.duration} />
    case "compaction":
      return <CompactionBadge summary={part.summary} />
    case "agent":
      return <AgentSwitchBadge agent={part.agent} />
    case "retry":
      return <RetryBadge attempt={part.attempt} reason={part.reason} />
    case "patch":
      return <PatchPart files={part.files} />
    case "plan":
      return <PlanCard part={part} sessionId={sessionId} />
    default:
      return null
  }
}
