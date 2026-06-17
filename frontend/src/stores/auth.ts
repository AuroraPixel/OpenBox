import { create } from "zustand"

interface AuthState {
  accessToken: string | null
  user: { id: string; username: string; email?: string; role: string } | null
  isAuthenticated: boolean
  isLoading: boolean

  setAuth: (token: string, user: AuthState["user"]) => void
  clearAuth: () => void
  setLoading: (loading: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  isLoading: true, // Start loading until we try refresh

  setAuth: (token, user) =>
    set({ accessToken: token, user, isAuthenticated: true, isLoading: false }),
  clearAuth: () =>
    set({ accessToken: null, user: null, isAuthenticated: false, isLoading: false }),
  setLoading: (loading) => set({ isLoading: loading }),
}))

// ── Token refresh with mutex ──

let refreshPromise: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = doRefresh().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

async function doRefresh(): Promise<string | null> {
  try {
    const BASE_URL = import.meta.env.VITE_API_URL || ""
    const resp = await fetch(`${BASE_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include", // Send HttpOnly cookie
    })
    if (!resp.ok) {
      useAuthStore.getState().clearAuth()
      return null
    }
    const data = await resp.json()
    const token = data.access_token
    // Fetch user info
    const meResp = await fetch(`${BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (meResp.ok) {
      const user = await meResp.json()
      useAuthStore.getState().setAuth(token, user)
    } else {
      useAuthStore.getState().setAuth(token, null)
    }
    return token
  } catch {
    useAuthStore.getState().clearAuth()
    return null
  }
}
