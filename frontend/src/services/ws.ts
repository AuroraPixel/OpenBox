/**
 * Main WebSocket client — replaces SSE for real-time bidirectional communication.
 *
 * Server → Client: session events, message deltas, tool status, permissions, questions
 * Client → Server: permission replies, question replies, abort, build trigger
 */

type EventHandler = (data: unknown) => void

const BASE_URL = import.meta.env.VITE_API_URL || ""

export class AgentWSClient {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private reconnectTimer: number | null = null
  private _connected = false
  private authFailed = false

  async connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return
    if (this.authFailed) return

    try {
      const { useAuthStore, refreshAccessToken } = await import("@/stores/auth")
      let token = useAuthStore.getState().accessToken

      const ticketUrl = `${BASE_URL}/api/auth/ticket`
      let ticketResp = await fetch(ticketUrl, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })

      if (ticketResp.status === 401 && token) {
        const newToken = await refreshAccessToken()
        if (newToken) {
          token = newToken
          ticketResp = await fetch(ticketUrl, {
            method: "POST",
            headers: { Authorization: `Bearer ${newToken}` },
          })
        }
      }

      if (ticketResp.status === 401) {
        this.authFailed = true
        useAuthStore.getState().clearAuth()
        window.location.hash = "#/login"
        return
      }

      let wsUrl: string
      const wsBase = (BASE_URL || window.location.origin).replace(/^http/, "ws")
      if (ticketResp.ok) {
        const { ticket } = await ticketResp.json()
        wsUrl = `${wsBase}/ws/agent?ticket=${ticket}`
      } else {
        wsUrl = `${wsBase}/ws/agent`
      }

      this.ws = new WebSocket(wsUrl)

      this.ws.onopen = () => {
        this._connected = true
        this.authFailed = false
        this.dispatch("__connected", {})
      }

      this.ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data)
          const { type, data } = parsed
          if (type) {
            this.dispatch(type, data)
          }
        } catch {
          // Ignore malformed messages
        }
      }

      this.ws.onclose = () => {
        this._connected = false
        this.dispatch("__disconnected", {})
        this.ws = null
        if (!this.authFailed) {
          if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
          this.reconnectTimer = window.setTimeout(() => this.connect(), 3000)
        }
      }

      this.ws.onerror = () => {
        // onclose will handle reconnection
      }
    } catch (e) {
      console.error("WS connect error:", e)
      if (!this.authFailed) {
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
        this.reconnectTimer = window.setTimeout(() => this.connect(), 3000)
      }
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
    this._connected = false
  }

  // ── Client → Server commands ──

  send(msg: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  replyPermission(id: string, action: string, message?: string) {
    this.send({ type: "permission.reply", id, action, message })
  }

  replyQuestion(id: string, answers: string[][]) {
    this.send({ type: "question.reply", id, answers })
  }

  rejectQuestion(id: string) {
    this.send({ type: "question.reject", id })
  }

  abortSession(sessionId: string) {
    this.send({ type: "session.abort", sessionId })
  }

  startBuild() {
    this.send({ type: "build.start" })
  }

  // ── Event subscription (same API as old SSEClient) ──

  on(event: string, handler: EventHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }
    this.handlers.get(event)!.add(handler)
    return () => this.off(event, handler)
  }

  off(event: string, handler: EventHandler) {
    this.handlers.get(event)?.delete(handler)
  }

  private dispatch(event: string, data: unknown) {
    this.handlers.get(event)?.forEach((handler) => {
      try {
        handler(data)
      } catch (e) {
        console.error(`WS handler error for event ${event}:`, e)
      }
    })
  }

  get connected() {
    return this._connected
  }
}

export const wsClient = new AgentWSClient()
