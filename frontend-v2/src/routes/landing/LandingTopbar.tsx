import { useTranslation } from "react-i18next"
import { BrandMark, LangPill } from "@/features/auth"
import { useStart } from "./useStart"

/** Sticky landing header: brand, section labels, language toggle, CTAs. */
export function LandingTopbar() {
  const { t } = useTranslation("landing")
  const start = useStart()
  const nav = t("nav", { returnObjects: true }) as unknown as { product: string; how: string; pricing: string }

  return (
    <header className="sticky top-0 z-20 flex-none border-b border-hair bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-15.5 max-w-[1080px] items-center gap-3 px-7">
        <BrandMark dot />
        <nav className="flex flex-1 justify-center gap-6.5">
          <span className="whitespace-nowrap text-sm text-n700">{nav.product}</span>
          <span className="whitespace-nowrap text-sm text-n700">{nav.how}</span>
          <span className="whitespace-nowrap text-sm text-n700">{nav.pricing}</span>
        </nav>
        <LangPill />
        <button type="button" onClick={start} className="flex-none px-1.5 text-sm text-n700 hover:text-ink">
          {t("signIn")}
        </button>
        <button
          type="button"
          onClick={start}
          className="flex-none rounded-full bg-ink px-4 py-2 text-sm text-bg hover:bg-a800"
        >
          {t("start")}
        </button>
      </div>
    </header>
  )
}
