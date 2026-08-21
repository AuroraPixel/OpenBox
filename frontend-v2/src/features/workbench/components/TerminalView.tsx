// xterm terminal bound to `/ws/terminal/{id}`. Lazily imported (see TerminalTab)
// so @xterm/* and its CSS stay out of the main bundle.
//
// Protocol (ported verbatim from v1 Terminal.tsx — the authority):
//   binary frames are raw PTY bytes prefixed by a 1-byte tag:
//     0x00 DATA   — payload is PTY bytes (both directions)
//     0x01 RESIZE — payload is cols/rows as two big-endian uint16 (client→server)
//   text frames are JSON and only carry errors: { type: "error", data }.
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Terminal as XTerm } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { fetchWsTicket, terminalWsUrl } from "@/features/workbench/utils/ws"
import "@xterm/xterm/css/xterm.css"

const MSG_DATA = 0x00
const MSG_RESIZE = 0x01

function readTermTheme(): { background: string; foreground: string; cursor: string } {
  const cs = getComputedStyle(document.documentElement)
  const background = cs.getPropertyValue("--t-term").trim() || "#26251f"
  const foreground = cs.getPropertyValue("--t-term-ink").trim() || "#e6e3dc"
  return { background, foreground, cursor: foreground }
}

function resizeFrame(cols: number, rows: number): Uint8Array<ArrayBuffer> {
  return new Uint8Array([MSG_RESIZE, (cols >> 8) & 0xff, cols & 0xff, (rows >> 8) & 0xff, rows & 0xff])
}

function dataFrame(text: string): Uint8Array<ArrayBuffer> {
  const bytes = new TextEncoder().encode(text)
  const buf = new Uint8Array(1 + bytes.length)
  buf[0] = MSG_DATA
  buf.set(bytes, 1)
  return buf
}

export default function TerminalView({ containerId }: { containerId: string }) {
  const { t } = useTranslation("workbench")
  const hostRef = useRef<HTMLDivElement>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    let socket: WebSocket | null = null
    let disposed = false

    const send = (frame: Uint8Array<ArrayBuffer>) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(frame)
    }

    const term = new XTerm({
      cursorBlink: true,
      cursorStyle: "bar",
      fontFamily: "var(--font-mono), ui-monospace, monospace",
      fontSize: 12.5,
      lineHeight: 1.4,
      theme: readTermTheme(),
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.loadAddon(new WebLinksAddon())
    term.open(host)
    try {
      fit.fit()
    } catch {
      /* host not measured yet */
    }

    const onData = term.onData((data) => send(dataFrame(data)))
    const onResize = term.onResize(({ cols, rows }) => send(resizeFrame(cols, rows)))
    const ro = new ResizeObserver(() => {
      try {
        fit.fit()
      } catch {
        /* ignore transient measure errors */
      }
    })
    ro.observe(host)

    void (async () => {
      const ticket = await fetchWsTicket()
      if (disposed || !ticket) return
      const ws = new WebSocket(terminalWsUrl(containerId, ticket))
      ws.binaryType = "arraybuffer"
      socket = ws
      ws.onopen = () => {
        setConnected(true)
        send(resizeFrame(term.cols, term.rows))
      }
      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          const bytes = new Uint8Array(ev.data)
          if (bytes.length && bytes[0] === MSG_DATA) term.write(bytes.subarray(1))
        } else {
          try {
            const msg = JSON.parse(ev.data as string) as { type?: string; data?: string }
            if (msg.type === "error") term.write(`\r\n\x1b[31m${msg.data ?? ""}\x1b[0m\r\n`)
          } catch {
            /* non-JSON text frame — ignore */
          }
        }
      }
      ws.onclose = () => setConnected(false)
      ws.onerror = () => ws.close()
    })()

    return () => {
      disposed = true
      onData.dispose()
      onResize.dispose()
      ro.disconnect()
      term.dispose()
      socket?.close()
    }
  }, [containerId])

  return (
    <div className="relative h-full w-full">
      <div ref={hostRef} className="h-full w-full" />
      {!connected && (
        <span className="absolute end-2 top-2 font-mono text-2xs text-termink">{t("terminal.connecting")}</span>
      )}
    </div>
  )
}
