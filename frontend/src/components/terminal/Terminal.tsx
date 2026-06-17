import { useState, useEffect, useRef, useCallback } from "react"
import { Terminal as XTerm } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { useWebSocket } from "@/hooks/useWebSocket"
import { api } from "@/services/api"
import { TERMINAL_MSG_DATA, TERMINAL_MSG_RESIZE } from "@/types"
import type { WSMessage } from "@/types"
import "@xterm/xterm/css/xterm.css"

interface TerminalProps {
  containerId: string
}

export function Terminal({ containerId }: TerminalProps) {
  const termRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)

  const sendResize = useCallback((cols: number, rows: number) => {
    const buf = new Uint8Array(5)
    buf[0] = TERMINAL_MSG_RESIZE
    buf[1] = (cols >> 8) & 0xff
    buf[2] = cols & 0xff
    buf[3] = (rows >> 8) & 0xff
    buf[4] = rows & 0xff
    sendBinaryRef.current?.(buf)
  }, [])

  const handleBinaryMessage = useCallback((data: ArrayBuffer) => {
    const term = xtermRef.current
    if (!term) return
    const bytes = new Uint8Array(data)
    if (bytes.length < 1) return
    const prefix = bytes[0]
    if (prefix === TERMINAL_MSG_DATA) {
      // PTY data - write directly to xterm
      term.write(bytes.subarray(1))
    }
  }, [])

  const handleMessage = useCallback((msg: WSMessage) => {
    // JSON messages are only for error notifications
    const term = xtermRef.current
    if (!term) return
    if (msg.type === "error") {
      term.write(`\r\n\x1b[31mError: ${msg.data}\x1b[0m\r\n`)
    }
  }, [])

  const [wsUrl, setWsUrl] = useState<string>("")
  useEffect(() => {
    api.getTerminalWsUrl(containerId).then(setWsUrl)
  }, [containerId])

  const { connected, connect, disconnect, sendBinary } = useWebSocket({
    url: wsUrl,
    onMessage: handleMessage,
    onBinaryMessage: handleBinaryMessage,
  })

  // Connect when wsUrl becomes available
  useEffect(() => {
    if (wsUrl) {
      connect()
    }
    return () => { disconnect() }
  }, [wsUrl])

  // Keep a ref to sendBinary so callbacks can access it without re-renders
  const sendBinaryRef = useRef(sendBinary)
  sendBinaryRef.current = sendBinary

  useEffect(() => {
    if (!termRef.current) return

    const xterm = new XTerm({
      cursorBlink: true,
      cursorStyle: "bar",
      fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
      fontSize: 13,
      lineHeight: 1.4,
      theme: {
        background: "#0a0e1a",
        foreground: "#c9d1d9",
        cursor: "#00e5ff",
        selectionBackground: "#264f78",
        black: "#0a0e1a",
        red: "#ff6b6b",
        green: "#39ff14",
        yellow: "#f5a623",
        blue: "#00e5ff",
        magenta: "#bc8cff",
        cyan: "#00e5ff",
        white: "#c9d1d9",
      },
    })

    const fitAddon = new FitAddon()
    xterm.loadAddon(fitAddon)
    xterm.loadAddon(new WebLinksAddon())

    xterm.open(termRef.current)
    fitAddon.fit()

    xtermRef.current = xterm
    fitAddonRef.current = fitAddon

    xterm.write("\x1b[1;36mOpenBox Sandbox Terminal\x1b[0m\r\n")
    xterm.write("Connecting...\r\n")

    // Send every keystroke directly to PTY
    const dataDisposable = xterm.onData((data) => {
      const encoder = new TextEncoder()
      const encoded = encoder.encode(data)
      const buf = new Uint8Array(1 + encoded.length)
      buf[0] = TERMINAL_MSG_DATA
      buf.set(encoded, 1)
      sendBinaryRef.current?.(buf)
    })

    // Handle binary sequences from xterm (mouse events, etc.)
    const binaryDisposable = xterm.onBinary((data) => {
      const bytes = new Uint8Array(data.length)
      for (let i = 0; i < data.length; i++) {
        bytes[i] = data.charCodeAt(i)
      }
      const buf = new Uint8Array(1 + bytes.length)
      buf[0] = TERMINAL_MSG_DATA
      buf.set(bytes, 1)
      sendBinaryRef.current?.(buf)
    })

    // Handle terminal resize
    const resizeDisposable = xterm.onResize(({ cols, rows }) => {
      const resizeBuf = new Uint8Array(5)
      resizeBuf[0] = TERMINAL_MSG_RESIZE
      resizeBuf[1] = (cols >> 8) & 0xff
      resizeBuf[2] = cols & 0xff
      resizeBuf[3] = (rows >> 8) & 0xff
      resizeBuf[4] = rows & 0xff
      sendBinaryRef.current?.(resizeBuf)
    })

    // Observe container resize to re-fit terminal
    const resizeObserver = new ResizeObserver(() => {
      try { fitAddon.fit() } catch {}
    })
    if (termRef.current) resizeObserver.observe(termRef.current)

    return () => {
      dataDisposable.dispose()
      binaryDisposable.dispose()
      resizeDisposable.dispose()
      resizeObserver.disconnect()
      xterm.dispose()
    }
  }, [containerId]) // eslint-disable-line

  // Send initial resize when connection is established
  useEffect(() => {
    if (connected && xtermRef.current) {
      const term = xtermRef.current
      sendResize(term.cols, term.rows)
    }
  }, [connected, sendResize])

  return (
    <div className="h-full w-full relative">
      <div ref={termRef} className="h-full w-full" />
      {!connected && (
        <div className="absolute top-3 right-3 text-[10px] font-mono uppercase tracking-wider bg-[hsl(var(--accent))]/15 text-[hsl(var(--accent))] px-3 py-1.5 rounded-sm border border-[hsl(var(--accent))]/20 backdrop-blur-sm animate-fade-in glow-amber">
          Reconnecting...
        </div>
      )}
    </div>
  )
}
