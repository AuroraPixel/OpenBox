// Dev-browser tab: address bar + a live screenshot stream over
// `/ws/dev-browser/auto`. Skin follows the design reference.
//
// PROTOCOL NOTE: v1 shipped no screenshot-stream client (its DevBrowserPanel is
// only a relay-enable control panel), so the frame/event wire format below is an
// assumption, not ported code:
//   • binary frames  → a JPEG/PNG image of the current page (rendered as-is);
//   • text frames    → JSON, `{type:"url"|"navigated", url}` updates the bar;
//   • client→server  → JSON: navigate/back/reload + click/scroll/key events;
//   • close code 4004 → no running sandbox.
// If the backend settles on a different shape, only this file needs to change.
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type WheelEvent as ReactWheelEvent,
} from "react"
import { useTranslation } from "react-i18next"
import { ChevronLeft, RotateCw } from "lucide-react"
import { useCreateContainer, useRunningContainer } from "@/features/workbench/api/containers"
import { devBrowserWsUrl, fetchWsTicket } from "@/features/workbench/utils/ws"
import { EmptyState } from "./EmptyState"

type Phase = "connecting" | "streaming" | "failed" | "noSandbox"

function frameCoords(img: HTMLImageElement, clientX: number, clientY: number) {
  const rect = img.getBoundingClientRect()
  const w = img.naturalWidth || rect.width
  const h = img.naturalHeight || rect.height
  return {
    x: Math.round(((clientX - rect.left) / rect.width) * w),
    y: Math.round(((clientY - rect.top) / rect.height) * h),
  }
}

interface StreamProps {
  onCreate: () => void
  creating: boolean
}

// Remounted via `key={containerId}` by the parent, so `phase` always starts at
// "connecting" — every transition happens inside an async WS callback, never
// synchronously in the effect body.
function BrowserStream({ onCreate, creating }: StreamProps) {
  const { t } = useTranslation("workbench")
  const [phase, setPhase] = useState<Phase>("connecting")
  const [urlInput, setUrlInput] = useState("")
  const imgRef = useRef<HTMLImageElement>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const frameUrlRef = useRef<string | null>(null)

  const send = useCallback((msg: Record<string, unknown>) => {
    const s = socketRef.current
    if (s?.readyState === WebSocket.OPEN) s.send(JSON.stringify(msg))
  }, [])

  useEffect(() => {
    let disposed = false
    let ws: WebSocket | null = null
    const clearFrame = () => {
      if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current)
      frameUrlRef.current = null
    }
    void (async () => {
      const ticket = await fetchWsTicket()
      if (disposed) return
      if (!ticket) {
        setPhase("failed")
        return
      }
      ws = new WebSocket(devBrowserWsUrl(ticket))
      ws.binaryType = "arraybuffer"
      socketRef.current = ws
      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          const url = URL.createObjectURL(new Blob([ev.data], { type: "image/jpeg" }))
          clearFrame()
          frameUrlRef.current = url
          if (imgRef.current) imgRef.current.src = url
          setPhase((p) => (p === "streaming" ? p : "streaming"))
        } else {
          try {
            const m = JSON.parse(ev.data as string) as { type?: string; url?: string }
            if ((m.type === "url" || m.type === "navigated") && m.url) setUrlInput(m.url)
          } catch {
            /* ignore non-JSON text */
          }
        }
      }
      ws.onclose = (ev) => {
        if (!disposed) setPhase(ev.code === 4004 ? "noSandbox" : "failed")
      }
      ws.onerror = () => ws?.close()
    })()
    return () => {
      disposed = true
      ws?.close()
      socketRef.current = null
      clearFrame()
    }
  }, [])

  // Apply the latest frame once the <img> exists (reading refs in an effect is ok).
  useEffect(() => {
    if (phase === "streaming" && imgRef.current && frameUrlRef.current) {
      imgRef.current.src = frameUrlRef.current
    }
  }, [phase])

  if (phase === "noSandbox") {
    return (
      <EmptyState
        title={t("sandbox.none")}
        action={{ label: t("sandbox.create"), onClick: onCreate, pending: creating }}
      />
    )
  }

  const onImgClick = (e: ReactMouseEvent<HTMLImageElement>) => {
    if (!imgRef.current) return
    send({ type: "click", ...frameCoords(imgRef.current, e.clientX, e.clientY), button: e.button })
  }
  const onImgWheel = (e: ReactWheelEvent<HTMLImageElement>) => {
    send({ type: "scroll", dx: Math.round(e.deltaX), dy: Math.round(e.deltaY) })
  }
  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key.length === 1 || e.key === "Enter" || e.key === "Backspace") send({ type: "key", key: e.key })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5 px-3 pb-3">
      <div className="flex flex-none items-center gap-2">
        <button
          type="button"
          onClick={() => send({ type: "back" })}
          title={t("action.back", { ns: "common" })}
          aria-label={t("action.back", { ns: "common" })}
          className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
        >
          <ChevronLeft size={15} strokeWidth={2.6} />
        </button>
        <input
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && urlInput.trim()) send({ type: "navigate", url: urlInput.trim() })
          }}
          placeholder={t("browser.placeholder")}
          className="h-8 min-w-0 flex-1 rounded-full border border-hair bg-card px-3.5 font-mono text-xs text-n700 outline-none"
        />
        <button
          type="button"
          onClick={() => send({ type: "reload" })}
          title={t("action.reload", { ns: "common" })}
          aria-label={t("action.reload", { ns: "common" })}
          className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
        >
          <RotateCw size={14} strokeWidth={2.6} />
        </button>
      </div>
      <div
        tabIndex={0}
        onKeyDown={onKeyDown}
        className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-hair bg-card outline-none"
      >
        {phase === "streaming" ? (
          <img
            ref={imgRef}
            alt={t("browser.empty")}
            onClick={onImgClick}
            onWheel={onImgWheel}
            onContextMenu={(e) => e.preventDefault()}
            className="max-h-full max-w-full object-contain"
          />
        ) : (
          <span className="text-sm text-n600">
            {phase === "failed" ? t("browser.failed") : t("browser.loading")}
          </span>
        )}
      </div>
    </div>
  )
}

export function BrowserTab() {
  const { t } = useTranslation("workbench")
  const running = useRunningContainer()
  const create = useCreateContainer()

  if (!running) {
    return (
      <EmptyState
        title={t("sandbox.none")}
        action={{
          label: t("sandbox.create"),
          onClick: () => create.mutate(undefined),
          pending: create.isPending,
        }}
      />
    )
  }

  return (
    <BrowserStream key={running.id} onCreate={() => create.mutate(undefined)} creating={create.isPending} />
  )
}
