import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useAppearanceStore } from "@/shared/appearance/store"
import { cn } from "@/shared/lib/cn"
import { buildTimeline, typed, RUNNING_GLYPH, STEP_GLYPHS } from "./mockTimeline"

function Caret() {
  return <span className="ms-0.5 inline-block h-3 w-0.5 animate-blink bg-n600 align-[-2px]" />
}

function MockSidebar() {
  const { t } = useTranslation("landing")
  const projects = t("mock.projects", { returnObjects: true }) as unknown as string[]
  return (
    <div className="flex w-52 flex-none flex-col gap-2 border-e border-hair bg-rail px-3 py-3.5">
      <div className="flex h-7.5 items-center justify-center rounded-full bg-ink text-2xs text-bg">
        {t("mock.new")}
      </div>
      {projects.map((name, i) => (
        <div
          key={name}
          className={cn(
            "flex h-7 items-center gap-2 rounded-full px-2.5 text-xs text-n800",
            i === 0 && "bg-n300",
          )}
        >
          <span className="text-2xs text-n500">{i === 0 ? "▾" : "▸"}</span>
          <span className="min-w-0 flex-1 truncate">{name}</span>
        </div>
      ))}
    </div>
  )
}

export function LandingMock() {
  const { t } = useTranslation("landing")
  const language = useAppearanceStore((s) => s.language)
  const isEn = language === "en-US"
  const tl = useMemo(() => buildTimeline((k: string) => t(k), isEn), [t, isEn])
  const reduced = useMemo(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches, [])
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (reduced) return
    const id = window.setInterval(() => setTick((m) => m + 90), 90)
    return () => window.clearInterval(id)
  }, [reduced])

  // Reduced motion shows the finished frame; otherwise loop over the timeline.
  const ms = reduced ? tl.finalFrame : tick % tl.period

  const showAsk = ms > 260
  const askCaret = ms > 260 && ms < tl.askDone + 120
  const showThink = ms > tl.thinkAt
  const thinking = ms <= tl.stepsEnd
  const showAnswer = ms > tl.answerAt
  const answerCaret = ms > tl.answerAt && ms < tl.answerDone + 200
  const showDiff = ms > tl.answerDone + 320
  const steps = tl.steps
    .map((s, i) => ({ visible: ms > s.at, running: ms < s.at + s.dur, glyph: STEP_GLYPHS[i], label: t(`mock.step${i + 1}`), ms: s.ms }))
    .filter((s) => s.visible)

  return (
    <section className="mx-auto mt-13.5 max-w-[1080px] px-7">
      <div className="overflow-hidden rounded-[20px] border border-hair bg-card shadow-float">
        <div className="flex h-9.5 items-center gap-2 border-b border-hair bg-rail px-3.5">
          <span className="size-2 rounded-full bg-n300" />
          <span className="size-2 rounded-full bg-n300" />
          <span className="size-2 rounded-full bg-n300" />
          <span className="ms-2 text-2xs text-n600">{t("mock.label")}</span>
        </div>

        <div className="flex h-[348px]">
          <MockSidebar />

          <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-hidden px-5.5 py-4.5">
            {showAsk && (
              <div className="animate-fade-up self-end max-w-[74%] rounded-xl rounded-ee-sm bg-n200 px-3.5 py-2 text-xs leading-relaxed">
                {typed(tl.askFull, 260, ms, tl.cps)}
                {askCaret && <Caret />}
              </div>
            )}

            {showThink && (
              <div className="flex animate-fade-up items-center gap-2 text-2xs text-n600">
                <span className={cn("size-1.5 rounded-full bg-n500", thinking && "animate-pulse-dot")} />
                <span>{thinking ? t("mock.thinking") : t("mock.thought")}</span>
              </div>
            )}

            <div className="flex flex-col gap-2">
              {steps.map((s) => (
                <div
                  key={s.glyph}
                  className="flex h-7 animate-fade-up items-center gap-2 rounded-md border border-hair px-3 text-2xs text-n700"
                >
                  <span
                    className={cn("inline-block font-mono", s.running ? "text-n700 animate-spin-arc" : "text-n500")}
                  >
                    {s.running ? RUNNING_GLYPH : s.glyph}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{s.label}</span>
                  {!s.running && <span className="text-2xs text-n500">{s.ms}</span>}
                </div>
              ))}
            </div>

            {showAnswer && (
              <div className="max-w-[96%] text-xs leading-loose text-ink">
                {typed(tl.ansFull, tl.answerAt, ms, tl.ansCps)}
                {answerCaret && <Caret />}
              </div>
            )}

            {showDiff && (
              <div className="flex animate-fade-up items-center gap-2.5 rounded-lg border border-hair bg-rail px-3 py-2">
                <span className="font-mono text-2xs text-n500">±</span>
                <span className="min-w-0 flex-1 truncate font-mono text-2xs">{t("mock.diff")}</span>
                <span className="flex-none text-2xs text-n600">+42 −11</span>
                <span className="flex-none text-2xs text-a700">{t("mock.review")}</span>
              </div>
            )}

            <div className="mt-auto flex h-9.5 items-center rounded-full border border-hair px-3.5 text-2xs text-n500">
              {t("mock.input")}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
