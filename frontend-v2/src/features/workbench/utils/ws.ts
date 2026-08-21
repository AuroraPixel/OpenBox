// WebSocket ticket + URL helpers for the terminal and dev-browser streams.
// Handshake mirrors the shared ws client and v1: POST /api/auth/ticket with the
// bearer token (one refresh retry), then pass the one-time ticket in the URL so
// the token never appears in a WS URL (ENGINEERING_SPEC §12.1).
import { env, wsBase } from "@/shared/config/env"
import { refreshAccessToken, useAuthStore } from "@/shared/api/auth-store"

async function requestTicket(token: string): Promise<Response> {
  return fetch(`${env.apiBase}/api/auth/ticket`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

/** Resolve a one-time WS ticket, or null when unauthenticated. */
export async function fetchWsTicket(): Promise<string | null> {
  let token = useAuthStore.getState().accessToken
  if (!token) token = await refreshAccessToken()
  if (!token) return null

  let resp = await requestTicket(token)
  if (resp.status === 401) {
    const next = await refreshAccessToken()
    if (!next) return null
    resp = await requestTicket(next)
  }
  if (!resp.ok) return null

  const { ticket } = (await resp.json()) as { ticket: string }
  return ticket
}

export function terminalWsUrl(containerId: string, ticket: string): string {
  return `${wsBase()}/ws/terminal/${containerId}?ticket=${ticket}`
}

export function devBrowserWsUrl(ticket: string): string {
  return `${wsBase()}/ws/dev-browser/auto?ticket=${ticket}`
}
