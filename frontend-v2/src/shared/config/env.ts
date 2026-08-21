// Single place that reads import.meta.env (ENGINEERING_SPEC §5.3).
export const env = {
  apiBase: (import.meta.env.VITE_API_URL as string | undefined) ?? "",
} as const

export function wsBase(): string {
  return (env.apiBase || window.location.origin).replace(/^http/, "ws")
}
