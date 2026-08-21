// Left "+" menu: upload a file, or grab a screen frame. Screenshot uses
// getDisplayMedia → draw one video frame to a canvas → PNG File, and the menu
// item hides entirely when the browser can't offer it.
import { useRef, useState } from "react"
import { Crop, Plus, Upload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import { toast } from "@/shared/ui/Toast"

interface Props {
  disabled?: boolean
  title?: string
  onFiles: (files: File[]) => void
}

const canScreenshot = (): boolean =>
  typeof navigator !== "undefined" && typeof navigator.mediaDevices?.getDisplayMedia === "function"

async function captureScreenshot(): Promise<File | null> {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true })
  try {
    const video = document.createElement("video")
    video.srcObject = stream
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error("video load failed"))
    })
    await video.play()
    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext("2d")
    if (!ctx) return null
    ctx.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"))
    if (!blob) return null
    return new File([blob], `screenshot-${Date.now()}.png`, { type: "image/png" })
  } finally {
    for (const track of stream.getTracks()) track.stop()
  }
}

export function ComposerActions({ disabled, title, onFiles }: Props) {
  const { t } = useTranslation("chat")
  const [open, setOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const onScreenshot = async () => {
    setOpen(false)
    try {
      const file = await captureScreenshot()
      if (file) onFiles([file])
      else toast("error", t("composer.screenshotFailed"))
    } catch {
      toast("error", t("composer.screenshotFailed"))
    }
  }

  return (
    <div className="relative flex-none">
      <input
        ref={fileRef}
        type="file"
        multiple
        hidden
        onChange={(e) => {
          onFiles([...(e.target.files ?? [])])
          e.target.value = ""
        }}
      />
      <Menu open={open} onClose={() => setOpen(false)} className="bottom-10 start-0 w-44">
        <MenuItem
          onClick={() => {
            setOpen(false)
            fileRef.current?.click()
          }}
        >
          <span className="flex items-center gap-2.5">
            <Upload className="size-4 flex-none" />
            {t("composer.uploadFile")}
          </span>
        </MenuItem>
        {canScreenshot() && (
          <MenuItem onClick={() => void onScreenshot()}>
            <span className="flex items-center gap-2.5">
              <Crop className="size-4 flex-none" />
              {t("composer.screenshot")}
            </span>
          </MenuItem>
        )}
      </Menu>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        title={title}
        aria-label={t("composer.tools")}
        className="text-n700 hover:bg-hairsoft flex size-8 items-center justify-center rounded-full disabled:opacity-40"
      >
        <Plus className="size-4.5" strokeWidth={2.4} />
      </button>
    </div>
  )
}
