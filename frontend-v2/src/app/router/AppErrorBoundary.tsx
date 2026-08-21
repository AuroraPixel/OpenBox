import { useTranslation } from "react-i18next"
import { Link, useRouteError } from "react-router"
import { paths } from "@/app/router/paths"

export function AppErrorBoundary() {
  const { t } = useTranslation("common")
  const error = useRouteError()
  console.error("[route error]", error)
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-bg">
      <span className="text-2xl font-medium text-ink">{t("state.error")}</span>
      <Link to={paths.app} className="rounded-full bg-ink px-5 py-2 text-md text-bg">
        {t("action.back")}
      </Link>
    </div>
  )
}
