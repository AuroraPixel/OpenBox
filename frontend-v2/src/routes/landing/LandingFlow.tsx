import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"

const NUMS = ["01", "02", "03"]

export function LandingFlow() {
  const { t } = useTranslation("landing")
  const steps = t("steps", { returnObjects: true }) as unknown as { title: string; body: string }[]
  return (
    <section className="mx-auto mt-22 max-w-[1080px] px-7">
      <div className="flex flex-col items-start gap-11 border-t border-hair pt-8.5 md:flex-row">
        <div className="flex w-full flex-none flex-col gap-2.5 md:w-65">
          <span className="text-xs text-n600">{t("flowEyebrow")}</span>
          <h2 className="text-pretty text-3xl leading-tight">{t("flowTitle")}</h2>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          {steps.map((s, i) => (
            <div key={s.title} className={cn("flex gap-4 py-5", i > 0 && "border-t border-hair")}>
              <span className="w-6 flex-none font-mono text-xs text-n500">{NUMS[i]}</span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="text-base">{s.title}</span>
                <p className="mt-1.5 text-pretty text-sm leading-relaxed text-n700">{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
