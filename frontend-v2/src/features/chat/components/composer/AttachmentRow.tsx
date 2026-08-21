// Horizontal strip of pending attachment cards above the textarea. Each card
// shows a type-derived icon, the name (shimmering while it uploads), and the
// size — or a red failure line if the sandbox rejected it.
import type { ComponentType } from "react"
import { FileArchive, FileCode, FileText, Image as ImageIcon, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { formatBytes } from "@/shared/lib/format"
import type { PendingAttachment } from "../../hooks/useAttachments"

const IMAGE_RE = /\.(png|jpe?g|gif|webp|svg|bmp|avif|ico)$/i
const CODE_RE = /\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|c|cc|cpp|h|hpp|css|scss|html?|json|ya?ml|toml|sh|rb|php|sql|md|vue|swift)$/i
const ARCHIVE_RE = /\.(zip|tar|gz|tgz|rar|7z|bz2|xz|zst)$/i

function iconFor(name: string): ComponentType<{ className?: string }> {
  if (IMAGE_RE.test(name)) return ImageIcon
  if (ARCHIVE_RE.test(name)) return FileArchive
  if (CODE_RE.test(name)) return FileCode
  return FileText
}

interface Props {
  items: PendingAttachment[]
  onRemove: (id: string) => void
}

export function AttachmentRow({ items, onRemove }: Props) {
  const { t } = useTranslation("chat")
  if (items.length === 0) return null

  return (
    <div className="scr flex gap-2 overflow-x-auto px-3 pt-3">
      {items.map((item) => {
        const Icon = iconFor(item.name)
        const failed = item.status === "error"
        const uploading = item.status === "uploading"
        return (
          <div
            key={item.id}
            className="group/att relative flex h-14 min-w-45 max-w-60 items-center gap-2.5 rounded-xl border border-hair bg-n200/40 px-2.5"
            title={`${item.name} · ${formatBytes(item.size)}`}
          >
            {item.preview ? (
              <img src={item.preview} alt="" className="size-9 flex-none rounded-lg object-cover" />
            ) : (
              <Icon className={cn("size-4 flex-none", failed ? "text-dangerink" : "text-n600")} />
            )}
            <div className="flex min-w-0 flex-1 flex-col pe-4">
              <span
                className={cn(
                  "truncate text-xs font-medium",
                  failed ? "text-dangerink" : "text-ink",
                  uploading && "text-shimmer",
                )}
              >
                {item.name}
              </span>
              <span className={cn("truncate text-2xs", failed ? "text-danger" : "text-n600")}>
                {failed
                  ? t("attachFailed")
                  : uploading
                    ? `${Math.round(item.progress * 100)}%`
                    : formatBytes(item.size)}
              </span>
            </div>
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              aria-label={t("common:action.delete", { ns: "common" })}
              className="text-n600 hover:bg-hairsoft hover:text-ink absolute end-1 top-1 flex size-5 items-center justify-center rounded-full opacity-0 transition-opacity group-hover/att:opacity-100"
            >
              <X className="size-3" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
