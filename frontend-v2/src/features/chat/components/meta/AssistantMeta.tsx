// Meta strip under an assistant turn: data badges (model / tokens / latency)
// stacked over the action row (copy, react, fork) and the timestamp.
import { Check, Copy, GitFork, ThumbsDown, ThumbsUp } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { useCopy } from "@/shared/hooks/useCopy"
import { paths } from "@/shared/router/paths"
import type { MessageReaction, TokenUsage } from "@/shared/types/api"
import { useForkMessage, useSetReaction } from "../../api/message-actions"
import { useStreamStore } from "../../stores/stream"
import { LatencyBadge, MessageTimestamp, ModelBadge, TokenBadge } from "./MetaBadges"
import { MetaContainer } from "./MetaContainer"
import { MetaIconButton } from "./MetaIconButton"

interface Props {
  sessionId: string
  messageId: string
  content: string
  tokens?: TokenUsage | null
  reaction?: MessageReaction
  createdAt: string
  streaming: boolean
  durationSec: number
}

export function AssistantMeta({
  sessionId,
  messageId,
  content,
  tokens,
  reaction,
  createdAt,
  streaming,
  durationSec,
}: Props) {
  const { t } = useTranslation("chat")
  const { copied, copy } = useCopy()
  const navigate = useNavigate()
  const setReaction = useStreamStore((s) => s.setMessageReaction)
  const { mutate: react } = useSetReaction(sessionId)
  const { mutate: fork, isPending: forking } = useForkMessage(sessionId)
  const current = reaction ?? null

  const toggleReaction = (next: Exclude<MessageReaction, null>) => {
    const value: MessageReaction = current === next ? null : next
    setReaction(sessionId, messageId, value) // optimistic
    react(
      { messageId, reaction: value },
      { onError: () => setReaction(sessionId, messageId, current) },
    )
  }

  const onFork = () => {
    fork(messageId, { onSuccess: (session) => navigate(paths.chat(session.id)) })
  }

  return (
    <MetaContainer align="start">
      <div className="flex min-w-0 max-w-full flex-col items-start gap-1.5">
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1">
          <ModelBadge sessionId={sessionId} />
          {tokens ? <TokenBadge tokens={tokens} /> : null}
          <LatencyBadge createdAt={createdAt} streaming={streaming} durationSec={durationSec} />
        </div>
        <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1">
          <MetaIconButton
            label={copied ? t("meta.copied") : t("meta.copyReply")}
            disabled={!content.trim()}
            onClick={() => copy(content)}
          >
            {copied ? (
              <Check size={14} strokeWidth={1.8} />
            ) : (
              <Copy size={14} strokeWidth={1.8} />
            )}
          </MetaIconButton>
          <MetaIconButton
            label={t("meta.likeReply")}
            active={current === "up"}
            disabled={streaming}
            onClick={() => toggleReaction("up")}
          >
            <ThumbsUp size={14} strokeWidth={1.8} />
          </MetaIconButton>
          <MetaIconButton
            label={t("meta.dislikeReply")}
            active={current === "down"}
            disabled={streaming}
            onClick={() => toggleReaction("down")}
          >
            <ThumbsDown size={14} strokeWidth={1.8} />
          </MetaIconButton>
          <MetaIconButton
            label={forking ? t("meta.forking") : t("meta.forkMessage")}
            disabled={streaming || forking}
            onClick={onFork}
          >
            <GitFork size={14} strokeWidth={1.8} />
          </MetaIconButton>
          <MessageTimestamp iso={createdAt} />
        </div>
      </div>
    </MetaContainer>
  )
}
