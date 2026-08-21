import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "@/shared/ui/Toast"
import { useLogtoConfig } from "@/features/auth/api/auth"
import { beginLogtoLogin } from "@/features/auth/lib/logto"

/** Divider + single-sign-on button. Renders nothing when Logto is disabled. */
export function SsoButton() {
  const { t } = useTranslation("auth")
  const { data: config } = useLogtoConfig()
  const [busy, setBusy] = useState(false)
  if (!config) return null

  const onClick = async () => {
    setBusy(true)
    try {
      await beginLogtoLogin(config) // navigates away on success
    } catch {
      setBusy(false)
      toast("error", t("errors.ssoFailed"))
    }
  }

  return (
    <>
      <div className="my-5 flex items-center gap-3">
        <span className="h-px flex-1 bg-hair" />
        <span className="text-2xs text-n600">{t("or")}</span>
        <span className="h-px flex-1 bg-hair" />
      </div>
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-hair bg-card text-sm text-ink hover:bg-hairsoft disabled:opacity-60"
      >
        <span className="font-mono text-2xs text-n600">⊕</span>
        <span>{busy ? t("ssoRedirecting") : t("sso")}</span>
      </button>
    </>
  )
}
