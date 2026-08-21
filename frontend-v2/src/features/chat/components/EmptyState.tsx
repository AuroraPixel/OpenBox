import { useTranslation } from "react-i18next"
import { useAuthStore } from "@/shared/api/auth-store"

interface Suggestion {
  title: string
  hint: string
}

function timeOfDay(): "morning" | "afternoon" | "evening" {
  const h = new Date().getHours()
  if (h < 12) return "morning"
  if (h < 18) return "afternoon"
  return "evening"
}

interface Props {
  projectName?: string
  onPick: (text: string) => void
}

/** New-chat greeting: time-based hello, project hint and clickable suggestions. */
export function EmptyState({ projectName, onPick }: Props) {
  const { t } = useTranslation("workspace")
  const username = useAuthStore((s) => s.user?.username ?? "")
  const greeting = t(`greeting.${timeOfDay()}`, { name: username })
  const hint = t("emptyHint", { project: projectName ?? t("unsorted") })
  const suggestions = t("suggestions", { returnObjects: true }) as unknown as Suggestion[]

  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center px-6.5 pb-10">
      <div className="mx-auto flex w-full max-w-190 flex-col gap-6.5">
        <h1 className="text-hero font-medium tracking-tight">{greeting}</h1>
        <p className="text-n700 max-w-120 text-base leading-[1.7]">{hint}</p>
        <div className="mt-1 flex flex-col gap-0.5">
          {Array.isArray(suggestions) &&
            suggestions.map((g, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onPick(g.title)}
                className="hover:bg-hairsoft flex min-h-11.5 items-center gap-3.5 rounded-full px-4 text-start"
              >
                <span className="bg-s400 size-2 flex-none rounded-full" />
                <span className="flex-none text-base">{g.title}</span>
                <span className="text-n600 min-w-0 flex-1 truncate text-sm">{g.hint}</span>
              </button>
            ))}
        </div>
      </div>
    </div>
  )
}
