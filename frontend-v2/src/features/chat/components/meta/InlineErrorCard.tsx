// Rendered under the turn body when an assistant message carried an error.
import { CircleAlert } from "lucide-react"
import { useTranslation } from "react-i18next"

function extractErrorMessage(error: Record<string, unknown>): string {
  const message = error.message
  if (typeof message === "string" && message.trim()) return message
  const nested = error.error
  if (typeof nested === "string" && nested.trim()) return nested
  try {
    return JSON.stringify(error)
  } catch {
    return ""
  }
}

export function InlineErrorCard({ error }: { error: Record<string, unknown> }) {
  const { t } = useTranslation("chat")
  const message = extractErrorMessage(error)
  return (
    <div className="border-hair bg-dangersoft mt-2 flex gap-3 rounded-xl border px-4 py-3">
      <CircleAlert className="text-danger mt-0.5 size-4 shrink-0" strokeWidth={1.8} />
      <div className="min-w-0">
        <p className="text-dangerink text-md font-medium">{t("meta.errorTitle")}</p>
        {message && <p className="text-n700 text-md mt-0.5 [overflow-wrap:anywhere]">{message}</p>}
      </div>
    </div>
  )
}
