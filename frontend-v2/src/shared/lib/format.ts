// All date/number formatting goes through here with the active locale
// (ENGINEERING_SPEC §10.6) — never bare toLocaleString().
import i18n from "@/shared/i18n"

function locale(): string {
  return i18n.language || "zh-CN"
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(locale(), { dateStyle: "medium", timeStyle: "short" }).format(new Date(iso))
}

export function formatRelative(iso: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale(), { numeric: "auto" })
  const diff = (new Date(iso).getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  if (abs < 60) return rtf.format(Math.round(diff), "second")
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute")
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour")
  return rtf.format(Math.round(diff / 86400), "day")
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat(locale()).format(n)
}

export function formatTokens(n: number): string {
  if (n >= 1000) return `${new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(n / 1000)}k`
  return String(n)
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.min(sizes.length - 1, Math.floor(Math.log(bytes) / Math.log(k)))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export function formatDuration(seconds: number): string {
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  if (seconds < 60) return `${Math.round(seconds)}s`
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

export function formatCost(usd: number): string {
  return new Intl.NumberFormat(locale(), { style: "currency", currency: "USD", maximumFractionDigits: 3 }).format(usd)
}
