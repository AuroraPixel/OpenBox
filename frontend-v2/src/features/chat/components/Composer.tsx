import { useEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { ArrowUp, Square } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { toast } from "@/shared/ui/Toast"
import { useConfigQuery } from "../api/config"
import { useRunningContainer } from "../api/containers"
import { useAttachments } from "../hooks/useAttachments"
import { useMentionMenu } from "../hooks/useMentionMenu"
import { useSendShortcut } from "../hooks/useSendShortcut"
import { useModelChoice } from "../hooks/useModelChoice"
import { useComposerDrop } from "../hooks/useComposerDrop"
import { InputGroup } from "./composer/InputGroup"
import { AttachmentRow } from "./composer/AttachmentRow"
import { ComposerActions } from "./composer/ComposerActions"
import { ModelPicker } from "./composer/ModelPicker"
import { ShortcutPicker } from "./composer/ShortcutPicker"
import { MentionMenu } from "./composer/MentionMenu"

export interface ComposerSubmit {
  model?: string
  /** OSS asset ids of the message's attachments. */
  attachments?: string[]
}

interface Props {
  busy: boolean
  onSubmit: (text: string, opts: ComposerSubmit) => void
  onStop?: () => void
  autoFocus?: boolean
  /** The model this conversation last used. Each session carries its own, so
   *  reopening one restores that choice rather than the global default. */
  sessionModel?: string
  /** Changes when the user moves to another conversation, which resets the
   *  picker — an unsent choice belongs to the chat it was made in. */
  sessionKey?: string
  /** G2's mention/command menu mounts here — it renders inside the relative
   *  anchor that wraps the textarea, so it can position against the input. */
  mentionSlot?: ReactNode
}

const MAX_UPLOAD = 8 * 1024 * 1024
const MAX_HEIGHT = 200 // matches max-h-50

/** Design composer: a single focus-owning shell (InputGroup) holding the
 *  attachment strip, the chromeless textarea, and one action row whose sole
 *  round button morphs between send and stop. */
export function Composer({ busy, onSubmit, onStop, autoFocus, mentionSlot, sessionModel, sessionKey }: Props) {
  const { t } = useTranslation("chat")
  const { data: config } = useConfigQuery()
  const models = config?.models ?? []
  const [text, setText] = useState("")
  const [caret, setCaret] = useState(0)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const composing = useRef(false)

  const running = useRunningContainer()
  const attachments = useAttachments(running?.id ?? null)
  const shortcut = useSendShortcut()

  const { activeId, pick } = useModelChoice({
    sessionModel,
    sessionKey,
    fallback: config?.default_model ?? models[0]?.id,
  })

  const pickFiles = (files: File[]) => {
    const ok = files.filter((f) => {
      if (f.size > MAX_UPLOAD) {
        toast("error", t("attachTooLarge"))
        return false
      }
      return true
    })
    attachments.addFiles(ok)
  }

  const drop = useComposerDrop({ enabled: !!running, onFiles: pickFiles })

  const mention = useMentionMenu({
    text,
    caret,
    textareaRef: taRef,
    containerId: running?.id ?? null,
    onReplace: (nextText, nextCaret) => {
      setText(nextText)
      setCaret(nextCaret)
    },
  })

  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = "auto"
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  const canSend = (text.trim().length > 0 || attachments.items.length > 0) && !attachments.uploading
  const showStop = busy && !!onStop

  const submit = () => {
    if (!canSend) return
    onSubmit(attachments.decorate(text.trim()), { model: activeId, attachments: attachments.assetIds() })
    setText("")
    attachments.clear()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // IME double-guard: React's composing flag plus the legacy 229 keyCode.
    if (composing.current || e.nativeEvent.isComposing || e.keyCode === 229) return
    // The open menu owns ↑↓/Enter/Tab/Esc so picking an item never sends.
    if (mention.onKeyDown(e)) return
    if (shortcut.matches(e)) {
      e.preventDefault()
      submit()
    }
  }

  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = [...e.clipboardData.files]
    if (files.length === 0 || !running) return
    // Let a genuine text paste through; only intercept pure file payloads.
    if (!e.clipboardData.getData("text/plain")) e.preventDefault()
    pickFiles(files)
  }

  const placeholder = drop.dragging
    ? t("composer.dropTitle")
    : busy
      ? t("composer.placeholderRunning")
      : t("composer.placeholder")

  return (
    <div className="flex-none px-6.5 pt-1 pb-5">
      <div className="mx-auto w-full max-w-190">
        <InputGroup dragging={drop.dragging} {...drop.dragHandlers}>
          <AttachmentRow items={attachments.items} onRemove={attachments.remove} />

          {/* Mention-menu anchor: relative so G2 can absolutely-position its
              popover against the textarea. */}
          <div className="relative">
            <textarea
              ref={taRef}
              value={text}
              autoFocus={autoFocus}
              rows={1}
              onChange={(e) => {
                setText(e.target.value)
                setCaret(e.target.selectionStart ?? e.target.value.length)
              }}
              onSelect={(e) => setCaret(e.currentTarget.selectionStart ?? 0)}
              onKeyDown={onKeyDown}
              onPaste={onPaste}
              onCompositionStart={() => (composing.current = true)}
              onCompositionEnd={() => (composing.current = false)}
              placeholder={placeholder}
              className={cn(
                "scr text-ink placeholder:text-n700 max-h-50 min-h-12 w-full resize-none border-none bg-transparent px-5 text-lg leading-6 outline-none transition-[height]",
                attachments.items.length > 0 ? "pt-2" : "pt-4",
              )}
            />
            {mention.open && (
              <MentionMenu
                sections={mention.sections}
                activeIndex={mention.activeIndex}
                onActiveIndexChange={mention.setActiveIndex}
                onSelect={mention.select}
              />
            )}
            {mentionSlot}
          </div>

          <div className="flex items-center gap-1 px-3 pb-1">
            <ComposerActions
              disabled={!running}
              title={running ? t("attachTitle") : t("attachNeedSandbox")}
              onFiles={pickFiles}
            />

            <ModelPicker models={models} activeId={activeId} onPick={pick} />
            <ShortcutPicker shortcut={shortcut.shortcut} onChange={shortcut.setShortcut} />

            <button
              type="button"
              onClick={showStop ? onStop : submit}
              disabled={!showStop && !canSend}
              aria-label={showStop ? t("composer.stop") : t("send")}
              className="bg-ink text-bg flex size-10 flex-none items-center justify-center rounded-full transition-opacity disabled:opacity-40"
            >
              {showStop ? (
                <Square className="size-3.5 fill-current" strokeWidth={0} />
              ) : (
                <ArrowUp className="size-4.5" strokeWidth={2.75} />
              )}
            </button>
          </div>

          <div className="flex justify-end px-4 pb-1.5">
            <span className="text-n600 text-2xs">
              {t(shortcut.shortcut === "mod_enter" ? "composer.sendShortcut.hintModEnter" : "composer.sendShortcut.hintEnter")}
            </span>
          </div>
        </InputGroup>
      </div>
    </div>
  )
}
