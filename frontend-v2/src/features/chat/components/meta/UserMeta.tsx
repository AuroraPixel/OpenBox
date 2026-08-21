// Meta strip under a user bubble: right-aligned copy button + timestamp.
// User messages carry no reaction/fork semantics, so those actions are omitted.
import { Check, Copy } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useCopy } from "@/shared/hooks/useCopy"
import { MessageTimestamp } from "./MetaBadges"
import { MetaContainer } from "./MetaContainer"
import { MetaIconButton } from "./MetaIconButton"

export function UserMeta({ content, createdAt }: { content: string; createdAt: string }) {
  const { t } = useTranslation("chat")
  const { copied, copy } = useCopy()
  return (
    <MetaContainer align="end">
      <MessageTimestamp iso={createdAt} />
      <MetaIconButton
        label={copied ? t("meta.copied") : t("meta.copyReply")}
        disabled={!content.trim()}
        onClick={() => copy(content)}
      >
        {copied ? <Check size={14} strokeWidth={1.8} /> : <Copy size={14} strokeWidth={1.8} />}
      </MetaIconButton>
    </MetaContainer>
  )
}
