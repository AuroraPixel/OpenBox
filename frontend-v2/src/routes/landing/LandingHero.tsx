import { useTranslation } from "react-i18next"
import { useStart } from "./useStart"

export function LandingHero() {
  const { t } = useTranslation("landing")
  const start = useStart()
  return (
    <section className="mx-auto flex max-w-[1080px] flex-col items-center px-7 pt-23 text-center">
      <span className="inline-flex h-7 items-center gap-2 rounded-full border border-hair bg-card px-3.5 text-xs text-n700">
        {t("badge")}
      </span>
      <h1 className="mt-6.5 max-w-[780px] text-pretty text-display">{t("heroTitle")}</h1>
      <p className="mt-5 max-w-[600px] text-pretty text-lg text-n700">{t("heroBody")}</p>
      <div className="mt-7.5 flex items-center gap-3">
        <button
          type="button"
          onClick={start}
          className="h-10.5 rounded-full bg-ink px-5.5 text-base text-bg hover:bg-a800"
        >
          {t("ctaPrimary")}
        </button>
        <button
          type="button"
          onClick={start}
          className="h-10.5 rounded-full border border-hair bg-card px-5 text-base text-ink hover:bg-hairsoft"
        >
          {t("ctaSecondary")}
        </button>
      </div>
      <span className="mt-3.5 text-xs text-n600">{t("ctaNote")}</span>
    </section>
  )
}
