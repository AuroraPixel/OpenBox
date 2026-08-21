// i18n bootstrap. Namespaces load lazily per feature (ENGINEERING_SPEC §10.2)
// through a tiny vite-backed loader — no extra backend dependency needed.
import i18n from "i18next"
import { initReactI18next } from "react-i18next"

export const SUPPORTED_LANGS = ["zh-CN", "en-US"] as const
export type AppLanguage = (typeof SUPPORTED_LANGS)[number]

const LANG_KEY = "bossip:lang"

const localeModules = import.meta.glob<{ default: Record<string, unknown> }>("../../locales/*/*.json")

const lazyBackend = {
  type: "backend" as const,
  init() {
    // no-op
  },
  read(lng: string, ns: string, callback: (err: unknown, data: unknown) => void) {
    const loader = localeModules[`../../locales/${lng}/${ns}.json`]
    if (!loader) {
      callback(new Error(`missing locale bundle ${lng}/${ns}`), null)
      return
    }
    loader().then(
      (mod) => callback(null, mod.default),
      (err) => callback(err, null),
    )
  },
}

export function detectInitialLanguage(): AppLanguage {
  const stored = localStorage.getItem(LANG_KEY)
  if (stored === "zh-CN" || stored === "en-US") return stored
  return navigator.language.toLowerCase().startsWith("zh") ? "zh-CN" : "en-US"
}

export function persistLanguage(lang: AppLanguage): void {
  localStorage.setItem(LANG_KEY, lang)
  document.documentElement.lang = lang
}

void i18n
  .use(lazyBackend)
  .use(initReactI18next)
  .init({
    lng: detectInitialLanguage(),
    fallbackLng: "en-US",
    supportedLngs: [...SUPPORTED_LANGS],
    ns: ["common"],
    defaultNS: "common",
    interpolation: { escapeValue: false },
    react: { useSuspense: true },
    partialBundledLanguages: true,
  })

export default i18n
