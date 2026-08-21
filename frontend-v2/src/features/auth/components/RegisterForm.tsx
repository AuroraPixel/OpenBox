import { useState, type FormEvent } from "react"
import { Link } from "react-router"
import { useTranslation } from "react-i18next"
import { paths } from "@/shared/router/paths"
import { useRegister, useCompleteAuth } from "@/features/auth/api/auth"
import { useAuthErrorMessage } from "@/features/auth/lib/errors"
import { TextField, PasswordField } from "@/features/auth/components/AuthFields"

/** Card content for the register route (AuthShell supplies the card shell). */
export function RegisterForm() {
  const { t } = useTranslation("auth")
  const register = useRegister()
  const complete = useCompleteAuth()
  const toMessage = useAuthErrorMessage()

  const [account, setAccount] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState("")

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!account.trim() || !password) {
      setError(t("errors.required"))
      return
    }
    if (password !== confirm) {
      setError(t("errors.pwMismatch"))
      return
    }
    setError("")
    register.mutate(
      { username: account.trim(), password, email: email.trim() || undefined },
      { onSuccess: (data) => void complete(data), onError: (err) => setError(toMessage(err)) },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col">
      <h1 className="text-3xl">{t("registerTitle")}</h1>
      <p className="mt-2 text-sm text-n700">{t("registerBody")}</p>

      <div className="mt-6">
        <TextField
          label={t("accountLabel")}
          value={account}
          onChange={setAccount}
          placeholder={t("accountPlaceholder")}
          autoComplete="username"
        />
        <TextField
          label={t("emailLabel")}
          value={email}
          onChange={setEmail}
          placeholder={t("emailPlaceholder")}
          type="email"
          autoComplete="email"
        />
        <PasswordField
          label={t("pwLabel")}
          value={password}
          onChange={setPassword}
          placeholder={t("pwPlaceholder")}
          autoComplete="new-password"
        />
        <PasswordField
          label={t("pwConfirmLabel")}
          value={confirm}
          onChange={setConfirm}
          placeholder={t("pwConfirmPlaceholder")}
          autoComplete="new-password"
        />
      </div>

      {error && <p className="mt-3 text-2xs text-danger">{error}</p>}

      <button
        type="submit"
        disabled={register.isPending}
        className="mt-5 h-11 rounded-lg bg-ink text-sm font-medium text-bg hover:bg-a800 disabled:opacity-60"
      >
        {register.isPending ? t("signingIn") : t("registerBtn")}
      </button>

      <span className="mt-5 text-2xs leading-relaxed text-n600">{t("legal")}</span>
      <Link to={paths.login} className="mt-3.5 text-xs text-a700 hover:text-ink">
        {t("haveAccount")}
      </Link>
    </form>
  )
}
