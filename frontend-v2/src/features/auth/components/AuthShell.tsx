import type { ReactNode } from "react"
import { Link } from "react-router"
import { useTranslation } from "react-i18next"
import { paths } from "@/shared/router/paths"
import { BrandMark } from "@/features/auth/components/BrandMark"
import { LangPill } from "@/features/auth/components/LangPill"
import { LoginGrid } from "@/features/auth/components/LoginGrid"

/** Full-page auth chrome: animated grid backdrop, top bar, centered card. */
export function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation("auth")
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-bg text-ink">
      <LoginGrid />

      <header className="relative z-10 flex h-15.5 flex-none items-center gap-3 px-7.5">
        <BrandMark />
        <div className="flex-1" />
        <LangPill />
        <Link to={paths.landing} className="flex-none px-1 text-2xs text-n700 hover:text-ink">
          {t("backHome")}
        </Link>
      </header>

      <div className="relative z-10 flex flex-1 items-center justify-center px-7 pt-6 pb-18">
        <div className="flex w-full max-w-98 flex-col rounded-2xl border border-hair bg-card/85 px-8 pt-8.5 pb-7.5 shadow-login backdrop-blur-md animate-fade-up">
          {children}
        </div>
      </div>
    </div>
  )
}
