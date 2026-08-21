import { useTranslation } from "react-i18next"

const GLYPHS = ["▤", "⌕", "±"] // per-card monospace marks (design order)

export function LandingFeatures() {
  const { t } = useTranslation("landing")
  const features = t("features", { returnObjects: true }) as unknown as { title: string; body: string }[]
  return (
    <section className="mx-auto mt-24 max-w-[1080px] px-7">
      <span className="text-xs text-n600">{t("featEyebrow")}</span>
      <div className="mt-4.5 grid grid-cols-1 gap-3.5 md:grid-cols-3">
        {features.map((f, i) => (
          <div
            key={f.title}
            className="flex flex-col gap-2.5 rounded-xl border border-hair bg-card px-5.5 pt-5.5 pb-6"
          >
            <span className="font-mono text-sm text-n500">{GLYPHS[i]}</span>
            <h3 className="text-lg">{f.title}</h3>
            <p className="text-pretty text-sm leading-relaxed text-n700">{f.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
