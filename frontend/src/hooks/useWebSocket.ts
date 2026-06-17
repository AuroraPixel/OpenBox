import { useRef, useState, useCallback, useEffect } from "react"
import type { WSMessage } from "@/types"

interface UseWebSocketOptions {
  url: string
  onMessage?: (msg: WSMessage) => void
  onBinaryMessage?: (data: ArrayBuffer) => void
  onOpen?: () => void
  onClose?: () => void
  reconnectInterval?: number
  maxRetries?: number
}

export function useWebSocket(options: UseWebSocketOptions) {
  const { url, onMessage, onBinaryMessage, onOpen, onClose, reconnectInterval = 3000, maxRetries = 5 } = options
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const retriesRef = useRef(0)
  const closedManuallyRef = useRef(false)

  const connect = useCallback(() => {
    if (!url) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    closedManuallyRef.current = false

    const ws = new WebSocket(url)
    ws.binaryType = "arraybuffer"
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retriesRef.current = 0
      onOpen?.()
    }

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        onBinaryMessage?.(event.data)
      } else {
        try {
          const msg: WSMessage = JSON.parse(event.data)
          onMessage?.(msg)
        } catch { /* ignore */ }
      }
    }

    ws.onclose = () => {
      setConnected(false)
      onClose?.()
      if (!closedManuallyRef.current && retriesRef.current < maxRetries) {
        retriesRef.current++
        setTimeout(connect, reconnectInterval)
      }
    }

    ws.onerror = () => {}
  }, [url, onMessage, onBinaryMessage, onOpen, onClose, reconnectInterval, maxRetries])

  const send = useCallback((msg: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const sendBinary = useCallback((data: Uint8Array | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  const disconnect = useCallback(() => {
    closedManuallyRef.current = true
    wsRef.current?.close()
  }, [])

  useEffect(() => {
    return () => {
      closedManuallyRef.current = true
      wsRef.current?.close()
    }
  }, [])

  return { connected, connect, disconnect, send, sendBinary }
}
