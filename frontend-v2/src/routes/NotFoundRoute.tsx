import { useTranslation } from "react-i18next"
import { Link } from "react-router"
import { paths } from "@/shared/router/paths"

export default function NotFoundRoute() {
  const { t } = useTranslation("common")
  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4 bg-bg">
      <span className="font-mono text-3xl text-n500">404</span>
      <span className="text-base text-n700">{t("state.empty")}</span>
      <Link to={paths.landing} className="rounded-full bg-ink px-5 py-2 text-md text-bg">
        bossip
      </Link>
    </div>
  )
}
