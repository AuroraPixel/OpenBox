import { useState, type FormEvent } from "react"
import { Link } from "react-router"
import { useTranslation } from "react-i18next"
import { paths } from "@/shared/router/paths"
import { cn } from "@/shared/lib/cn"
import { useLogin, useCompleteAuth } from "@/features/auth/api/auth"
import { useAuthErrorMessage } from "@/features/auth/lib/errors"
import { TextField, PasswordField } from "@/features/auth/components/AuthFields"
import { SsoButton } from "@/features/auth/components/SsoButton"

/** Card content for the login route (AuthShell supplies the card shell). */
export function LoginForm() {
  const { t } = useTranslation("auth")
  const login = useLogin()
  const complete = useCompleteAuth()
  const toMessage = useAuthErrorMessage()

  const [account, setAccount] = useState("")
  const [password, setPassword] = useState("")
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState("")

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!account.trim() || !password) {
      setError(t("errors.required"))
      return
    }
    setError("")
    login.mutate(
      { username: account.trim(), password },
      { onSuccess: (data) => void complete(data), onError: (err) => setError(toMessage(err)) },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col">
      <h1 className="text-3xl">{t("loginTitle")}</h1>
      <p className="mt-2 text-sm text-n700">{t("loginBody")}</p>

      <div className="mt-6">
        <TextField
          label={t("accountLabel")}
          value={account}
          onChange={setAccount}
          placeholder={t("accountPlaceholder")}
          autoComplete="username"
        />
        <PasswordField
          label={t("pwLabel")}
          value={password}
          onChange={setPassword}
          placeholder={t("pwPlaceholder")}
          autoComplete="current-password"
        />
      </div>

      <div className="mt-3.5 flex items-center gap-2">
        <button
          type="button"
          role="checkbox"
          aria-checked={remember}
          aria-label={t("remember")}
          onClick={() => setRemember((r) => !r)}
          className={cn(
            "flex size-4 flex-none items-center justify-center rounded-sm border text-2xs leading-none",
            remember ? "border-ink bg-ink text-bg" : "border-n400 text-transparent",
          )}
        >
          ✓
        </button>
        <button type="button" onClick={() => setRemember((r) => !r)} className="text-xs text-n700">
          {t("remember")}
        </button>
      </div>

      {error && <p className="mt-3 text-2xs text-danger">{error}</p>}

      <button
        type="submit"
        disabled={login.isPending}
        className="mt-5 h-11 rounded-lg bg-ink text-sm font-medium text-bg hover:bg-a800 disabled:opacity-60"
      >
        {login.isPending ? t("signingIn") : t("signInBtn")}
      </button>

      <SsoButton />

      <span className="mt-5 text-2xs leading-relaxed text-n600">{t("legal")}</span>
      <Link to={paths.register} className="mt-3.5 text-xs text-a700 hover:text-ink">
        {t("noAccount")}
      </Link>
    </form>
  )
}
