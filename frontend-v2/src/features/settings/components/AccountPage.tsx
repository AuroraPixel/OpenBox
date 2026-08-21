import { useTranslation } from "react-i18next"
import { useAuthStore } from "@/shared/api/auth-store"
import { RowCard, Row } from "./SettingsRow"

function Value({ children, mono }: { children: string; mono?: boolean }) {
  return (
    <span className={mono ? "flex-none font-mono text-2xs text-n600" : "flex-none text-sm text-n700"}>
      {children}
    </span>
  )
}

export function AccountPage() {
  const { t } = useTranslation("settings")
  const user = useAuthStore((s) => s.user)
  if (!user) return null
  return (
    <RowCard>
      <Row label={t("account.username")} right={<Value>{user.username}</Value>} />
      <Row label={t("account.email")} right={<Value>{user.email || t("account.emailNone")}</Value>} />
      <Row label={t("account.role")} right={<Value>{user.role}</Value>} />
      <Row label={t("account.userId")} right={<Value mono>{user.id}</Value>} />
    </RowCard>
  )
}
