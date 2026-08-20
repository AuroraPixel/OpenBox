/**
 * Logto OIDC sign-in (Authorization Code + PKCE, public client).
 *
 * The browser only builds the authorize URL and holds the PKCE verifier. The
 * code-for-token exchange happens on the OpenBox backend — Logto restricts CORS
 * to a fixed origin allowlist, so a server-to-server exchange is both simpler
 * and one fewer thing to keep in sync.
 */
const BASE_URL = import.meta.env.VITE_API_URL || ""

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

export async function getLogtoConfig(): Promise<LogtoConfig | null> {
  try {
    const resp = await fetch(`${BASE_URL}/api/auth/logto/config`)
    if (!resp.ok) return null
    const data = (await resp.json()) as LogtoConfig
    return data.enabled ? data : null
  } catch {
    return null
  }
}

function randomString(bytes = 32): string {
  const buf = new Uint8Array(bytes)
  crypto.getRandomValues(buf)
  return base64UrlEncode(buf)
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = ""
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")
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
  window.location.assign(`${config.endpoint}/oidc/auth?${params}`)
}

export function isLogtoCallback(): boolean {
  if (window.location.pathname !== "/callback") return false
  const q = new URLSearchParams(window.location.search)
  return q.has("code") || q.has("error")
}

export interface LogtoResult {
  access_token: string
  user: { id: string; username: string; email?: string; role: string }
}

/**
 * Finishes the redirect leg. Always clears the URL and the stashed PKCE state,
 * so a refresh on /callback can't replay a spent code.
 */
export async function completeLogtoLogin(): Promise<LogtoResult> {
  const q = new URLSearchParams(window.location.search)
  const verifier = sessionStorage.getItem(VERIFIER_KEY)
  const expectedState = sessionStorage.getItem(STATE_KEY)
  sessionStorage.removeItem(VERIFIER_KEY)
  sessionStorage.removeItem(STATE_KEY)
  window.history.replaceState({}, "", "/")

  const error = q.get("error")
  if (error) throw new Error(q.get("error_description") || error)

  const code = q.get("code")
  if (!code) throw new Error("Logto returned no authorization code")
  if (!verifier) throw new Error("Sign-in state was lost — please try again")
  if (!expectedState || q.get("state") !== expectedState) {
    throw new Error("Sign-in state mismatch — please try again")
  }

  const config = await getLogtoConfig()
  const resp = await fetch(`${BASE_URL}/api/auth/logto/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // backend sets the refresh_token cookie
    body: JSON.stringify({
      code,
      code_verifier: verifier,
      redirect_uri: config?.redirect_uri,
    }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `Sign-in failed (HTTP ${resp.status})`)
  }
  return resp.json()
}
