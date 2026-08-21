// 云桌面 tab: streams the sandbox's Wuying cloud desktop through Alibaba's
// Web SDK. The backend hands us a one-time connection ticket (202-pending
// retried here); the SDK renders the remote screen into an iframe we scale to
// fit. Read-only by default — the agent works on that desktop, so taking the
// mouse is an explicit choice. No machine ids ever reach the UI.
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Maximize2, Minimize2, RotateCw, Upload } from "lucide-react"
import { http, ApiError } from "@/shared/api/http"
import { Spinner } from "@/shared/ui/Spinner"
import { cn } from "@/shared/lib/cn"

const SDK_URL =
  "https://g.alicdn.com/aliyun-ecs/WuyingWebSdk-multi/2.12.5-asp3.18.7/WuyingWebSDK/WuyingWebSDK.js"
const SDK_PATH =
  "https://g.alicdn.com/aliyun-ecs/WuyingWebSdk-multi/2.12.5-asp3.18.7/WuyingWebSDK/sdk/ASP/container.html"
const FRAME_ID = "wuying-desktop-frame"
// The remote surface the SDK draws; everything is scaled from this.
const REMOTE_W = 1920
const REMOTE_H = 1080

interface WuyingSession {
  start: () => void
  stop?: () => void
  stopConnection?: () => void
  addHandle: (event: string, cb: (data?: { code?: string | number; message?: string }) => void) => void
  enableInput?: (on: boolean) => void
  setInputEnabled?: (on: boolean) => void
  setTouchEnabled?: (on: boolean) => void
  /** Two-way clipboard bridge between this page and the remote desktop. */
  setClipboardEnabled?: (on: boolean) => void
  /** Sends a local file to the desktop; showDialog surfaces remote progress UI. */
  uploadFile?: (file: File, showDialog: boolean) => void
}

interface WuyingGlobal {
  WebSDK?: { createSession: (id: string, opts: Record<string, unknown>) => WuyingSession }
}

interface Ticket {
  ticket?: string
  desktopId?: string
  regionId?: string
  pending?: boolean
  taskId?: string
}

let sdkLoading: Promise<void> | null = null
function loadSdk(): Promise<void> {
  const w = window as { Wuying?: WuyingGlobal }
  if (w.Wuying?.WebSDK) return Promise.resolve()
  sdkLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script")
    script.src = SDK_URL
    script.async = true
    script.onload = () => {
      if ((window as { Wuying?: WuyingGlobal }).Wuying?.WebSDK) resolve()
      else reject(new Error("sdk"))
    }
    script.onerror = () => {
      sdkLoading = null
      reject(new Error("sdk"))
    }
    document.head.appendChild(script)
  })
  return sdkLoading
}

/** Poll the ticket endpoint through its 202-pending window. */
async function fetchTicket(alive: () => boolean): Promise<Ticket> {
  let taskId = ""
  for (let attempt = 0; attempt < 30 && alive(); attempt += 1) {
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : ""
    const data = await http.get<Ticket>(`/api/desktop/ticket${query}`)
    if (data.ticket) return data
    taskId = data.taskId ?? taskId
    await new Promise((r) => setTimeout(r, 3000))
  }
  throw new Error("timeout")
}

type Phase = "loading" | "connected" | "error" | "closed"

type Fullscreen = "off" | "native" | "fallback"

export function DesktopTab() {
  const { t } = useTranslation("workbench")
  const rootRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const sessionRef = useRef<WuyingSession | null>(null)
  const [phase, setPhase] = useState<Phase>("loading")
  const [detail, setDetail] = useState("")
  const [control, setControl] = useState(false)
  const [clipboard, setClipboard] = useState(true)
  const [fs, setFs] = useState<Fullscreen>("off")
  const [attempt, setAttempt] = useState(0)
  // The connect effect outlives renders; mirror the toggles for it.
  const togglesRef = useRef({ control: false, clipboard: true })
  useEffect(() => {
    togglesRef.current = { control, clipboard }
  }, [control, clipboard])

  // (Re)connect whenever `attempt` bumps; tear the session down on unmount.
  // Phase starts as "loading" and the reconnect button resets it, so the
  // effect never needs to set state synchronously.
  useEffect(() => {
    let alive = true
    const stage = stageRef.current

    const stop = () => {
      const s = sessionRef.current
      sessionRef.current = null
      try {
        s?.stop?.()
        s?.stopConnection?.()
      } catch {
        // already gone
      }
    }

    void (async () => {
      try {
        const [, ticket] = await Promise.all([loadSdk(), fetchTicket(() => alive)])
        if (!alive || !stage) return

        stage.replaceChildren()
        const wrap = document.createElement("div")
        wrap.style.cssText = `position:absolute;top:0;left:0;width:${REMOTE_W}px;height:${REMOTE_H}px;transform-origin:0 0;`
        const frame = document.createElement("iframe")
        frame.id = FRAME_ID
        frame.title = t("desktop.frameTitle")
        frame.allow = "clipboard-read; clipboard-write; fullscreen"
        frame.style.cssText = "width:100%;height:100%;border:0;"
        wrap.appendChild(frame)
        stage.appendChild(wrap)

        const sdk = (window as { Wuying?: WuyingGlobal }).Wuying?.WebSDK
        if (!sdk) throw new Error("sdk")
        const session = sdk.createSession(`bossip-desktop-${Date.now()}`, {
          openType: "inline",
          iframeId: FRAME_ID,
          sdkPath: SDK_PATH,
          resourceType: "local",
          connectType: "desktop",
          regionId: ticket.regionId,
          userInfo: { ticket: ticket.ticket },
          desktopInfo: { desktopId: ticket.desktopId, loginRegionId: ticket.regionId },
          uiConfig: { toolbar: { visible: false }, exitCheck: false, reconnectType: "simple", resolutionType: "B" },
        })
        sessionRef.current = session
        session.addHandle("onConnected", () => {
          if (!alive || sessionRef.current !== session) return
          setPhase("connected")
          const { control: takeOver, clipboard: clip } = togglesRef.current
          try {
            session.enableInput?.(takeOver)
            session.setInputEnabled?.(takeOver)
            session.setClipboardEnabled?.(clip)
          } catch {
            // best effort — read-only by default
          }
        })
        session.addHandle("onDisConnected", () => {
          if (!alive || sessionRef.current !== session) return
          sessionRef.current = null
          setPhase("closed")
        })
        session.addHandle("onError", (err) => {
          if (!alive || sessionRef.current !== session) return
          setPhase("error")
          setDetail(String(err?.message ?? err?.code ?? ""))
        })
        session.start()
      } catch (e) {
        if (!alive) return
        setPhase("error")
        if (e instanceof ApiError) setDetail(t("desktop.unavailable"))
        else if (e instanceof Error && e.message === "sdk") setDetail(t("desktop.sdkFailed"))
      }
    })()

    return () => {
      alive = false
      stop()
    }
  }, [attempt, t])

  // Scale the fixed-size remote surface to fit the stage.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || typeof ResizeObserver === "undefined") return
    const apply = () => {
      const wrap = stage.firstElementChild as HTMLElement | null
      if (!wrap || !stage.clientWidth) return
      const scale = Math.min(stage.clientWidth / REMOTE_W, stage.clientHeight / REMOTE_H)
      const x = (stage.clientWidth - REMOTE_W * scale) / 2
      const y = (stage.clientHeight - REMOTE_H * scale) / 2
      wrap.style.transform = `translate(${x}px, ${y}px) scale(${scale})`
    }
    const ro = new ResizeObserver(apply)
    ro.observe(stage)
    const mo = new MutationObserver(apply)
    mo.observe(stage, { childList: true })
    return () => {
      ro.disconnect()
      mo.disconnect()
    }
  }, [])

  // Leaving native fullscreen (Esc or the button) must reset our state; a
  // fallback overlay handles Esc itself.
  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement) setFs((v) => (v === "native" ? "off" : v))
    }
    document.addEventListener("fullscreenchange", onChange)
    return () => document.removeEventListener("fullscreenchange", onChange)
  }, [])
  useEffect(() => {
    if (fs !== "fallback") return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFs("off")
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [fs])

  const toggleControl = (on: boolean) => {
    setControl(on)
    const s = sessionRef.current
    try {
      s?.enableInput?.(on)
      s?.setInputEnabled?.(on)
      s?.setTouchEnabled?.(on)
    } catch {
      // session mid-teardown
    }
  }

  const toggleClipboard = (on: boolean) => {
    setClipboard(on)
    try {
      sessionRef.current?.setClipboardEnabled?.(on)
    } catch {
      // session mid-teardown
    }
  }

  const toggleFullscreen = () => {
    if (fs === "native") {
      void document.exitFullscreen().catch(() => setFs("off"))
      return
    }
    if (fs === "fallback") {
      setFs("off")
      return
    }
    const root = rootRef.current
    if (!root) return
    root
      .requestFullscreen()
      .then(() => setFs("native"))
      // Browsers without the API (or that refuse it) get a fixed overlay.
      .catch(() => setFs("fallback"))
  }

  const onPickFile = () => {
    const file = fileRef.current?.files?.[0]
    if (fileRef.current) fileRef.current.value = ""
    if (!file) return
    try {
      // showDialog=true: the remote desktop surfaces its own progress UI.
      sessionRef.current?.uploadFile?.(file, true)
    } catch {
      // session mid-teardown
    }
  }

  return (
    <div
      ref={rootRef}
      className={cn(
        "flex min-h-0 flex-1 flex-col",
        fs === "fallback" ? "fixed inset-0 z-50 bg-bg p-3" : "px-3 pb-3",
        fs === "native" && "bg-bg p-3",
      )}
    >
      <div className="flex flex-none flex-wrap items-center gap-x-3 gap-y-1.5 pb-2.5">
        <span
          className={cn(
            "size-2 flex-none rounded-full",
            phase === "connected" ? "bg-s500" : phase === "loading" ? "bg-a400" : "bg-n400",
          )}
          aria-hidden
        />
        <span className="min-w-0 flex-1 truncate text-sm text-n700">
          {phase === "connected"
            ? control
              ? t("desktop.controlOn")
              : t("desktop.readonly")
            : t(`desktop.${phase}`)}
        </span>
        {phase === "connected" && (
          <>
            <label className="flex flex-none cursor-pointer items-center gap-1.5 text-sm text-n700">
              <input
                type="checkbox"
                checked={control}
                onChange={(e) => toggleControl(e.target.checked)}
                className="accent-a700"
              />
              {t("desktop.allowControl")}
            </label>
            <label className="flex flex-none cursor-pointer items-center gap-1.5 text-sm text-n700">
              <input
                type="checkbox"
                checked={clipboard}
                onChange={(e) => toggleClipboard(e.target.checked)}
                className="accent-a700"
              />
              {t("desktop.clipboard")}
            </label>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              title={t("desktop.upload")}
              aria-label={t("desktop.upload")}
              className="flex size-7 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
            >
              <Upload size={14.5} strokeWidth={2.2} />
            </button>
          </>
        )}
        <button
          type="button"
          onClick={toggleFullscreen}
          title={fs === "off" ? t("desktop.fullscreen") : t("desktop.exitFullscreen")}
          aria-label={fs === "off" ? t("desktop.fullscreen") : t("desktop.exitFullscreen")}
          className="flex size-7 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
        >
          {fs === "off" ? <Maximize2 size={14.5} strokeWidth={2.2} /> : <Minimize2 size={14.5} strokeWidth={2.2} />}
        </button>
        {(phase === "error" || phase === "closed") && (
          <button
            type="button"
            onClick={() => {
              setPhase("loading")
              setDetail("")
              setAttempt((n) => n + 1)
            }}
            className="flex flex-none items-center gap-1.5 rounded-full border border-hair px-3 py-1 text-sm text-n800 hover:bg-hairsoft"
          >
            <RotateCw size={13} strokeWidth={2.4} />
            {t("desktop.reconnect")}
          </button>
        )}
        <input ref={fileRef} type="file" onChange={onPickFile} className="hidden" aria-hidden tabIndex={-1} />
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-hair bg-card">
        <div ref={stageRef} className="absolute inset-0" data-testid="desktop-stage" />
        {phase !== "connected" && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-card">
            {phase === "loading" ? (
              <>
                <Spinner className="size-5" />
                <span className="text-sm text-n600">{t("desktop.loading")}</span>
              </>
            ) : (
              <>
                <span className="text-base text-n800">{t(`desktop.${phase}`)}</span>
                {detail && <span className="max-w-90 text-center text-sm text-n600">{detail}</span>}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
