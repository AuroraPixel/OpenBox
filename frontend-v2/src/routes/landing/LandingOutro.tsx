import { useTranslation } from "react-i18next"
import { useStart } from "./useStart"

export function LandingOutro() {
  const { t } = useTranslation("landing")
  const start = useStart()
  const links = t("footLinks", { returnObjects: true }) as unknown as {
    terms: string
    privacy: string
    contact: string
  }

  return (
    <>
      <section className="mx-auto mt-23 max-w-[1080px] px-7">
        <div className="flex flex-col items-center gap-7.5 rounded-2xl border border-hair bg-card px-10 py-11 md:flex-row">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <h2 className="text-3xl leading-tight">{t("endTitle")}</h2>
            <p className="max-w-[460px] text-pretty text-base leading-relaxed text-n700">{t("endBody")}</p>
          </div>
          <button
            type="button"
            onClick={start}
            className="h-11 flex-none rounded-full bg-ink px-6 text-base text-bg hover:bg-a800"
          >
            {t("ctaPrimary")}
          </button>
        </div>
      </section>

      <footer className="mx-auto mt-15 max-w-[1080px] px-7 pb-11.5">
        <div className="flex items-center gap-5.5 border-t border-hair pt-5.5">
          <span className="text-xs text-n600">{t("footer")}</span>
          <div className="ms-auto flex gap-5">
            <span className="text-xs text-n600">{links.terms}</span>
            <span className="text-xs text-n600">{links.privacy}</span>
            <span className="text-xs text-n600">{links.contact}</span>
          </div>
        </div>
      </footer>
    </>
  )
}
