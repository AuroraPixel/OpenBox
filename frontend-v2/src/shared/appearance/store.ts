// Appearance = theme × mode × font-size × language. One of the three
// allowed app-global stores (ENGINEERING_SPEC §7.5). Applies data-attrs on
// <html>; persists locally at once and to server prefs when authenticated.
import { create } from "zustand"
import i18n, { persistLanguage, type AppLanguage } from "@/shared/i18n"
import { http } from "@/shared/api/http"
import type { UserPreferences } from "@/shared/types/api"

export const THEMES = ["default", "azure", "cobalt", "graphite", "lagoon", "ink", "ochre", "sepia"] as const
export type ThemeName = (typeof THEMES)[number]
export type ColorMode = "light" | "system" | "dark"
export type FontSize = "sm" | "base" | "md" | "lg"

// Swatch pills shown on the theme cards (from the design's themeDefs).
export const THEME_META: Record<ThemeName, { temp: "warm" | "cool" | "neutral"; pills: [string, string] }> = {
  default: { temp: "warm", pills: ["#c67139", "#2c2b28"] },
  azure: { temp: "cool", pills: ["#3ba0ff", "#1c1f22"] },
  cobalt: { temp: "cool", pills: ["#1a48d0", "#191c22"] },
  graphite: { temp: "neutral", pills: ["#111111", "#3d3d3d"] },
  lagoon: { temp: "cool", pills: ["#12b39a", "#17332e"] },
  ink: { temp: "cool", pills: ["#101215", "#2c3138"] },
  ochre: { temp: "warm", pills: ["#f07c0a", "#28221a"] },
  sepia: { temp: "warm", pills: ["#8a5f52", "#2c2320"] },
}

const LOCAL_KEY = "bossip:appearance"

interface AppearanceState {
  theme: ThemeName
  mode: ColorMode
  fontSize: FontSize
  language: AppLanguage
  setTheme: (t: ThemeName) => void
  setMode: (m: ColorMode) => void
  setFontSize: (f: FontSize) => void
  setLanguage: (l: AppLanguage) => void
  hydrateFromServer: (prefs: UserPreferences) => void
}

function readLocal(): Partial<Pick<AppearanceState, "theme" | "mode" | "fontSize">> {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) ?? "{}") as Partial<AppearanceState>
  } catch {
    return {}
  }
}

const media = window.matchMedia("(prefers-color-scheme: dark)")

function applyDom(theme: ThemeName, mode: ColorMode, fontSize: FontSize): void {
  const el = document.documentElement
  if (theme === "default") el.removeAttribute("data-theme")
  else el.setAttribute("data-theme", theme)
  const dark = mode === "dark" || (mode === "system" && media.matches)
  if (dark) el.setAttribute("data-mode", "dark")
  else el.removeAttribute("data-mode")
  if (fontSize === "base") el.removeAttribute("data-fs")
  else el.setAttribute("data-fs", fontSize)
}

function persist(state: Pick<AppearanceState, "theme" | "mode" | "fontSize" | "language">): void {
  localStorage.setItem(
    LOCAL_KEY,
    JSON.stringify({ theme: state.theme, mode: state.mode, fontSize: state.fontSize }),
  )
  // Server prefs are best-effort: appearance must work signed-out too.
  void http
    .put("/api/auth/me/preferences", {
      theme: state.theme,
      extra: { mode: state.mode, fontSize: state.fontSize, locale: state.language },
    })
    .catch(() => undefined)
}

export const useAppearanceStore = create<AppearanceState>((set, get) => {
  const local = readLocal()
  const initial = {
    theme: (THEMES as readonly string[]).includes(local.theme ?? "") ? (local.theme as ThemeName) : "default",
    mode: (["light", "system", "dark"] as const).includes(local.mode as ColorMode)
      ? (local.mode as ColorMode)
      : "system",
    fontSize: (["sm", "base", "md", "lg"] as const).includes(local.fontSize as FontSize)
      ? (local.fontSize as FontSize)
      : "base",
    language: (i18n.language === "en-US" ? "en-US" : "zh-CN") as AppLanguage,
  }
  applyDom(initial.theme, initial.mode, initial.fontSize)
  media.addEventListener("change", () => {
    const s = get()
    applyDom(s.theme, s.mode, s.fontSize)
  })

  const commit = (patch: Partial<AppearanceState>) => {
    set(patch)
    const s = get()
    applyDom(s.theme, s.mode, s.fontSize)
    persist(s)
  }

  return {
    ...initial,
    setTheme: (theme) => commit({ theme }),
    setMode: (mode) => commit({ mode }),
    setFontSize: (fontSize) => commit({ fontSize }),
    setLanguage: (language) => {
      set({ language })
      void i18n.changeLanguage(language)
      persistLanguage(language)
      const s = get()
      persist(s)
    },
    hydrateFromServer: (prefs) => {
      const extra = (prefs.extra ?? {}) as Record<string, unknown>
      const patch: Partial<AppearanceState> = {}
      if (typeof prefs.theme === "string" && (THEMES as readonly string[]).includes(prefs.theme))
        patch.theme = prefs.theme as ThemeName
      if (extra.mode === "light" || extra.mode === "system" || extra.mode === "dark")
        patch.mode = extra.mode
      if (extra.fontSize === "sm" || extra.fontSize === "base" || extra.fontSize === "md" || extra.fontSize === "lg")
        patch.fontSize = extra.fontSize
      set(patch)
      const s = get()
      applyDom(s.theme, s.mode, s.fontSize)
      if (extra.locale === "zh-CN" || extra.locale === "en-US") {
        if (extra.locale !== s.language) {
          set({ language: extra.locale })
          void i18n.changeLanguage(extra.locale)
          persistLanguage(extra.locale)
        }
      }
      localStorage.setItem(
        LOCAL_KEY,
        JSON.stringify({ theme: get().theme, mode: get().mode, fontSize: get().fontSize }),
      )
    },
  }
})
