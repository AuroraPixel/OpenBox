import { useAppearanceStore } from "@/shared/appearance/store"
import { cn } from "@/shared/lib/cn"
import type { AppLanguage } from "@/shared/i18n"

// Fixed display glyphs — not translatable copy, so they live outside the JSON.
const LANGS: { id: AppLanguage; label: string }[] = [
  { id: "zh-CN", label: "中" },
  { id: "en-US", label: "EN" },
]

/** 中 / EN language toggle; drives the global appearance language. */
export function LangPill() {
  const language = useAppearanceStore((s) => s.language)
  const setLanguage = useAppearanceStore((s) => s.setLanguage)
  return (
    <div className="flex flex-none items-center gap-1 rounded-full border border-hair p-0.5">
      {LANGS.map((l) => (
        <button
          key={l.id}
          type="button"
          onClick={() => setLanguage(l.id)}
          className={cn(
            "flex h-6 min-w-7.5 items-center justify-center rounded-full text-xs",
            language === l.id ? "bg-ink text-bg" : "text-n700 hover:text-ink",
          )}
        >
          {l.label}
        </button>
      ))}
    </div>
  )
}
