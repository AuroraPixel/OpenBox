// The single WebSocket client (ENGINEERING_SPEC §12.1). Handshake uses a
// one-time ticket so tokens never appear in URLs; exponential backoff on
// reconnect; unknown events are ignored.
import { env, wsBase } from "@/shared/config/env"
import { refreshAccessToken, useAuthStore } from "@/shared/api/auth-store"
import type { WsEventMap, WsEventName } from "@/shared/ws/events"

type Handler<E extends WsEventName> = (data: WsEventMap[E]) => void

class AgentWsClient {
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<Handler<WsEventName>>>()
  private reconnectTimer: number | null = null
  private attempt = 0
  private closedByUser = false
  private _connected = false

  get connected() {
    return this._connected
  }

  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return
    this.closedByUser = false

    let token = useAuthStore.getState().accessToken
    if (!token) return

    let ticketResp = await fetch(`${env.apiBase}/api/auth/ticket`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    })
    if (ticketResp.status === 401) {
      const newToken = await refreshAccessToken()
      if (!newToken) return
      token = newToken
      ticketResp = await fetch(`${env.apiBase}/api/auth/ticket`, {
        method: "POST",
        headers: { Authorization: `Bearer ${newToken}` },
      })
    }
    if (!ticketResp.ok) {
      this.scheduleReconnect()
      return
    }

    const { ticket } = (await ticketResp.json()) as { ticket: string }
    this.ws = new WebSocket(`${wsBase()}/ws/agent?ticket=${ticket}`)

    this.ws.onopen = () => {
      this._connected = true
      this.attempt = 0
      this.dispatch("__connected", {})
    }
    this.ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data as string) as { type?: string; event?: string; data?: unknown }
        const name = parsed.type ?? parsed.event
        if (name) this.dispatch(name, parsed.data ?? parsed)
      } catch {
        // non-JSON frame — ignore
      }
    }
    this.ws.onclose = () => {
      this._connected = false
      this.ws = null
      this.dispatch("__disconnected", {})
      if (!this.closedByUser) this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  disconnect(): void {
    this.closedByUser = true
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
    this._connected = false
  }

  send(payload: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload))
  }

  on<E extends WsEventName>(event: E, handler: Handler<E>): () => void {
    const set = this.handlers.get(event) ?? new Set()
    set.add(handler as Handler<WsEventName>)
    this.handlers.set(event, set)
    return () => {
      set.delete(handler as Handler<WsEventName>)
    }
  }

  private dispatch(event: string, data: unknown): void {
    const set = this.handlers.get(event)
    if (!set) return
    for (const handler of set) {
      try {
        handler(data as WsEventMap[WsEventName])
      } catch (err) {
        // one bad handler must not break the stream
        console.error(`[ws] handler for ${event} threw`, err)
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer)
    const delay = Math.min(30_000, 1000 * 2 ** this.attempt)
    this.attempt += 1
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      void this.connect()
    }, delay)
  }
}

export const wsClient = new AgentWsClient()
