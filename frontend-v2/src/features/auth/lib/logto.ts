/**
 * Logto OIDC sign-in (Authorization Code + PKCE, public client).
 *
 * Ported from the v1 client (frontend/src/lib/logto.ts). The browser only
 * builds the authorize URL and holds the PKCE verifier; the code-for-token
 * exchange happens on the OpenBox backend — Logto restricts CORS to a fixed
 * origin allowlist, so a server-to-server exchange is simpler and safer.
 */
import { env } from "@/shared/config/env"
import type { AuthUser } from "@/shared/types/api"

const VERIFIER_KEY = "logto:code_verifier"
const STATE_KEY = "logto:state"

export interface LogtoConfig {
  enabled: boolean
  endpoint: string
  issuer: string
  app_id: string
  redirect_uri: string
  post_logout_redirect_uri: string
}

export interface LogtoResult {
  access_token: string
  user: AuthUser
}

/** Fetch the public PKCE config; returns null when Logto is disabled/unreachable. */
export async function getLogtoConfig(): Promise<LogtoConfig | null> {
  try {
    const resp = await fetch(`${env.apiBase}/api/auth/logto/config`)
    if (!resp.ok) return null
    const data = (await resp.json()) as LogtoConfig
    return data.enabled ? data : null
  } catch {
    return null
  }
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = ""
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
}

function randomString(bytes = 32): string {
  const buf = new Uint8Array(bytes)
  crypto.getRandomValues(buf)
  return base64UrlEncode(buf)
}

async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
  return base64UrlEncode(new Uint8Array(digest))
}

/** Redirects the browser to Logto. Does not return. */
export async function beginLogtoLogin(config: LogtoConfig): Promise<void> {
  const verifier = randomString(32)
  const state = randomString(16)
  sessionStorage.setItem(VERIFIER_KEY, verifier)
  sessionStorage.setItem(STATE_KEY, state)

  const params = new URLSearchParams({
    client_id: config.app_id,
    redirect_uri: config.redirect_uri,
    response_type: "code",
    scope: "openid profile email offline_access",
    state,
    code_challenge: await pkceChallenge(verifier),
    code_challenge_method: "S256",
    prompt: "consent",
  })
  window.location.assign(`${config.endpoint}/oidc/auth?${params.toString()}`)
}

/** True when the current URL carries a Logto authorization result. */
export function isLogtoCallback(): boolean {
  const q = new URLSearchParams(window.location.search)
  return q.has("code") || q.has("error")
}

/**
 * Finishes the redirect leg. Always clears the URL query and the stashed PKCE
 * state first, so a refresh on the callback route can't replay a spent code.
 */
export async function completeLogtoLogin(): Promise<LogtoResult> {
  const q = new URLSearchParams(window.location.search)
  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  const expectedState = sessionStorage.getItem(STATE_KEY)
  sessionStorage.removeItem(VERIFIER_KEY)
  sessionStorage.removeItem(STATE_KEY)
  // Strip the query string but stay on the callback path; the route navigates.
  window.history.replaceState({}, "", window.location.pathname)

  const error = q.get("error")
  if (error) throw new Error(q.get("error_description") || error)

  const code = q.get("code")
  if (!code) throw new Error("Logto returned no authorization code")
  if (!verifier) throw new Error("Sign-in state was lost — please try again")
  if (!expectedState || q.get("state") !== expectedState) {
    throw new Error("Sign-in state mismatch — please try again")
  }

  const config = await getLogtoConfig()
  const resp = await fetch(`${env.apiBase}/api/auth/logto/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // backend sets the refresh_token cookie
    body: JSON.stringify({ code, code_verifier: verifier, redirect_uri: config?.redirect_uri }),
  })
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => ({}))) as { detail?: string }
    throw new Error(detail.detail || `Sign-in failed (HTTP ${resp.status})`)
  }
  return (await resp.json()) as LogtoResult
}
