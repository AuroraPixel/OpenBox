// HTTP transport: auth header injection, one 401-refresh-retry, normalized
// errors (ApiError with a stable code for the i18n error map, §10.7).
import { env } from "@/shared/config/env"
import { refreshAccessToken, useAuthStore } from "@/shared/api/auth-store"

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = res.statusText
  let code = `HTTP_${res.status}`
  try {
    const body = (await res.json()) as { detail?: unknown; code?: unknown }
    if (typeof body.code === "string") code = body.code
    if (typeof body.detail === "string") detail = body.detail
    else if (body.detail) detail = JSON.stringify(body.detail)
  } catch {
    // non-JSON body — keep statusText
  }
  return new ApiError(res.status, code, detail)
}

async function doFetch(path: string, options: RequestInit, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) ?? {}),
  }
  if (token) headers.Authorization = `Bearer ${token}`
  return fetch(`${env.apiBase}${path}`, { ...options, headers, credentials: "include" })
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().accessToken
  let res = await doFetch(path, options, token)

  if (res.status === 401 && token) {
    const newToken = await refreshAccessToken()
    if (newToken) res = await doFetch(path, options, newToken)
  }

  if (!res.ok) throw await toApiError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
}
