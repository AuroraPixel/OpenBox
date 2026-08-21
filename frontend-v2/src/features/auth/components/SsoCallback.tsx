import { useEffect, useRef, useState } from "react"
import { Link } from "react-router"
import { useTranslation } from "react-i18next"
import { paths } from "@/shared/router/paths"
import { Spinner } from "@/shared/ui/Spinner"
import { useCompleteAuth } from "@/features/auth/api/auth"
import { completeLogtoLogin } from "@/features/auth/lib/logto"

/** Finishes the Logto redirect: exchange the code, sign in, route into the app. */
export function SsoCallback() {
  const { t } = useTranslation("auth")
  const complete = useCompleteAuth()
  const [failed, setFailed] = useState(false)
  const ran = useRef(false)

  useEffect(() => {
    // Guard against StrictMode's double-invoke: the code is single-use and the
    // URL is stripped on first run.
    if (ran.current) return
    ran.current = true
    completeLogtoLogin()
      .then((res) => complete(res))
      .catch(() => setFailed(true))
  }, [complete])

  if (failed) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl">{t("errors.ssoFailed")}</h1>
        <Link to={paths.login} className="text-xs text-a700 hover:text-ink">
          {t("haveAccount")}
        </Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 py-8">
      <Spinner className="size-6" />
      <span className="text-sm text-n700">{t("ssoRedirecting")}</span>
    </div>
  )
}
