import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
import {
  useAppearanceStore,
  THEMES,
  THEME_META,
  type ColorMode,
  type FontSize,
} from "@/shared/appearance/store"
import type { AppLanguage } from "@/shared/i18n"
import { cn } from "@/shared/lib/cn"

// Fixed preview values — data, not translatable copy.
const AA = "Aa"
const DARK_BG = "#1b1a18"
const DARK_INK = "#f3f1ec"
const SYSTEM_SPLIT = `linear-gradient(115deg, transparent 0 48%, ${DARK_BG} 48% 100%)`
const LANGS: AppLanguage[] = ["zh-CN", "en-US"]
const MODES: { id: ColorMode; glyph: string }[] = [
  { id: "light", glyph: "☀" },
  { id: "system", glyph: "▢" },
  { id: "dark", glyph: "☽" },
]
const FONTS: { id: FontSize; px: number }[] = [
  { id: "sm", px: 12.5 },
  { id: "base", px: 14 },
  { id: "md", px: 15.5 },
  { id: "lg", px: 17.5 },
]

const selBorder = (on: boolean) => (on ? "border-ink" : "border-hair")

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <span className="text-xs text-n600">{label}</span>
      {children}
    </div>
  )
}

function LangGrid() {
  const { t } = useTranslation("settings")
  const language = useAppearanceStore((s) => s.language)
  const setLanguage = useAppearanceStore((s) => s.setLanguage)
  const labels: Record<AppLanguage, string> = { "zh-CN": t("appearance.langZh"), "en-US": t("appearance.langEn") }
  return (
    <Section label={t("appearance.language")}>
      <div className="grid grid-cols-2 gap-2.5">
        {LANGS.map((id) => {
          const on = language === id
          return (
            <button
              key={id}
              type="button"
              onClick={() => setLanguage(id)}
              aria-pressed={on}
              className={cn("flex flex-col gap-1 rounded-lg border bg-card px-4 py-3.5 text-start", selBorder(on))}
            >
              <span className="text-base">{labels[id]}</span>
              <span className="text-xs text-n600">{on ? t("appearance.current") : ""}</span>
            </button>
          )
        })}
      </div>
    </Section>
  )
}

function ThemeGrid() {
  const { t } = useTranslation("settings")
  const theme = useAppearanceStore((s) => s.theme)
  const setTheme = useAppearanceStore((s) => s.setTheme)
  return (
    <Section label={t("appearance.theme")}>
      <div className="grid grid-cols-2 gap-2.5">
        {THEMES.map((k) => {
          const on = theme === k
          const meta = THEME_META[k]
          return (
            <button
              key={k}
              type="button"
              onClick={() => setTheme(k)}
              aria-label={k === "default" ? t("appearance.themeDefault") : k}
              aria-pressed={on}
              className={cn(
                "flex flex-col gap-3.5 rounded-lg border px-3.5 pt-3 pb-3.5 text-start",
                on ? "bg-hairsoft" : "bg-card",
                selBorder(on),
              )}
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-n200 px-2 py-0.5 text-2xs text-n700">
                  {t(`appearance.temp.${meta.temp}`)}
                </span>
                <span className="ms-auto flex gap-1">
                  <span className="h-5 w-2 rounded-full" style={{ background: meta.pills[0] }} />
                  <span className="h-5 w-2 rounded-full" style={{ background: meta.pills[1] }} />
                  <span className="h-5 w-2 rounded-full bg-n300" />
                  <span className="h-5 w-2 rounded-full bg-hair" />
                </span>
              </div>
              <span className="text-md font-medium">{k === "default" ? t("appearance.themeDefault") : k}</span>
            </button>
          )
        })}
      </div>
    </Section>
  )
}

function ModeGrid() {
  const { t } = useTranslation("settings")
  const mode = useAppearanceStore((s) => s.mode)
  const setMode = useAppearanceStore((s) => s.setMode)
  return (
    <Section label={t("appearance.colorMode")}>
      <div className="grid grid-cols-3 gap-2.5">
        {MODES.map(({ id, glyph }) => {
          const on = mode === id
          const dark = id === "dark"
          return (
            <button
              key={id}
              type="button"
              onClick={() => setMode(id)}
              aria-pressed={on}
              style={dark ? { background: DARK_BG } : undefined}
              className={cn(
                "relative flex h-15.5 items-center justify-center overflow-hidden rounded-lg border",
                !dark && "bg-card",
                selBorder(on),
              )}
            >
              {id === "system" && <span className="absolute inset-0" style={{ background: SYSTEM_SPLIT }} />}
              <span className="relative z-10 text-sm" style={dark ? { color: DARK_INK } : undefined}>
                {glyph} {t(`appearance.${id}`)}
              </span>
            </button>
          )
        })}
      </div>
    </Section>
  )
}

function FontGrid() {
  const { t } = useTranslation("settings")
  const fontSize = useAppearanceStore((s) => s.fontSize)
  const setFontSize = useAppearanceStore((s) => s.setFontSize)
  return (
    <Section label={t("appearance.fontSize")}>
      <div className="grid grid-cols-4 gap-2.5">
        {FONTS.map(({ id, px }) => (
          <button
            key={id}
            type="button"
            onClick={() => setFontSize(id)}
            aria-pressed={fontSize === id}
            style={{ fontSize: `${px}px` }}
            className={cn(
              "flex h-14.5 items-center justify-center rounded-lg border bg-card",
              fontSize === id ? "border-accent" : "border-hair",
            )}
          >
            {t(`appearance.fs.${id}`)} {AA}
          </button>
        ))}
      </div>
    </Section>
  )
}

export function AppearancePage() {
  return (
    <div className="flex flex-col gap-6">
      <LangGrid />
      <ThemeGrid />
      <ModeGrid />
      <FontGrid />
    </div>
  )
}
