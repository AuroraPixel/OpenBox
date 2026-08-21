// Image attachments as a gallery rather than a stack. A computer-use turn
// produces a screenshot per action, and one full-width card each pushed the
// actual answer off screen — so thumbnails tile three to a row, the first six
// show and the rest fold away. Clicking one opens it full size, which is also
// the only place a download belongs.
import { useCallback, useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { ChevronDown, Download, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { http } from "@/shared/api/http"
import { formatBytes } from "@/shared/lib/format"
import type { FilePart } from "@/shared/types/api"
import { useAssetUrl } from "../api/assets"

const VISIBLE_BY_DEFAULT = 6

function baseName(path: string): string {
  return path.split("/").pop() ?? path
}

function Thumb({ part, onOpen }: { part: FilePart; onOpen: () => void }) {
  const { t } = useTranslation("chat")
  const { data } = useAssetUrl(part.asset_id)
  const [broken, setBroken] = useState(false)
  const name = baseName(part.path)

  return (
    <button
      type="button"
      onClick={onOpen}
      title={name}
      aria-label={t("gallery.open", { name })}
      className="border-hair hover:border-n400 group/thumb relative aspect-video overflow-hidden rounded-lg border transition-colors"
    >
      {data?.url && !broken ? (
        <img
          src={data.url}
          alt={name}
          loading="lazy"
          onError={() => setBroken(true)}
          className="size-full object-cover"
        />
      ) : (
        <span className="bg-n200/50 text-n600 flex size-full items-center justify-center text-2xs">
          {broken ? t("gallery.failed") : ""}
        </span>
      )}
    </button>
  )
}

function Lightbox({ part, onClose }: { part: FilePart; onClose: () => void }) {
  const { t } = useTranslation("chat")
  const { data } = useAssetUrl(part.asset_id)
  const name = baseName(part.path)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const download = async () => {
    if (!part.asset_id) return
    // A fresh URL with content-disposition, so the browser saves rather than
    // navigates — the preview URL renders inline.
    const { url } = await http.get<{ url: string }>(`/api/assets/${part.asset_id}/url?download=true`)
    window.open(url, "_blank", "noopener")
  }

  return createPortal(
    <div
      className="bg-n900/70 fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 p-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-full min-h-0 max-w-full flex-col gap-2.5"
        role="dialog"
        aria-modal="true"
        aria-label={name}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-bg flex flex-none items-center gap-3">
          <span className="min-w-0 flex-1 truncate font-mono text-sm">{name}</span>
          {part.size ? <span className="text-2xs flex-none opacity-70">{formatBytes(part.size)}</span> : null}
          <button
            type="button"
            onClick={download}
            disabled={!part.asset_id}
            title={t("gallery.download")}
            aria-label={t("gallery.download")}
            className="hover:bg-bg/20 flex size-8 flex-none items-center justify-center rounded-full disabled:opacity-40"
          >
            <Download size={16} strokeWidth={2.2} />
          </button>
          <button
            type="button"
            onClick={onClose}
            title={t("gallery.close")}
            aria-label={t("gallery.close")}
            className="hover:bg-bg/20 flex size-8 flex-none items-center justify-center rounded-full"
          >
            <X size={16} strokeWidth={2.2} />
          </button>
        </div>
        {data?.url && (
          <img src={data.url} alt={name} className="min-h-0 rounded-xl object-contain" />
        )}
      </div>
    </div>,
    document.body,
  )
}

export function AttachmentGallery({ parts, className }: { parts: FilePart[]; className?: string }) {
  const { t } = useTranslation("chat")
  const [expanded, setExpanded] = useState(false)
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const close = useCallback(() => setOpenIndex(null), [])

  if (parts.length === 0) return null
  // Newest first. A computer-use turn appends a screenshot per action, so the
  // last one is the current state of the screen and the early ones are
  // history — showing the oldest six and folding the rest away hid exactly
  // the frame worth looking at.
  const ordered = [...parts].reverse()
  const shown = expanded ? ordered : ordered.slice(0, VISIBLE_BY_DEFAULT)
  const hidden = ordered.length - shown.length
  // One or two images are the subject, not a contact sheet — don't shrink
  // them into a third of the column just to keep the grid uniform.
  const columns = parts.length === 1 ? "grid-cols-1" : parts.length === 2 ? "grid-cols-2" : "grid-cols-3"

  return (
    <div className={cn("flex flex-col gap-1.5", parts.length === 1 ? "max-w-90" : "max-w-165", className)}>
      <div className={cn("grid gap-1.5", columns)}>
        {shown.map((part, i) => (
          <Thumb key={part.id} part={part} onOpen={() => setOpenIndex(i)} />
        ))}
      </div>
      {(hidden > 0 || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-n600 hover:text-ink inline-flex items-center gap-1 self-start text-xs transition-colors"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} strokeWidth={2} />
          {expanded ? t("gallery.less") : t("gallery.more", { count: hidden })}
        </button>
      )}
      {/* Indexes address `ordered`, not `parts` — opening the first thumbnail
          must show the newest image, not the oldest. */}
      {openIndex !== null && ordered[openIndex] && (
        <Lightbox part={ordered[openIndex]} onClose={close} />
      )}
    </div>
  )
}
