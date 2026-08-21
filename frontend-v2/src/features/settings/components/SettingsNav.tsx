import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { paths } from "@/shared/router/paths"
import { cn } from "@/shared/lib/cn"
import { SETTINGS_TABS, type SettingsTab } from "@/features/settings/tabs"

/** Left rail of pill-shaped tab links. */
export function SettingsNav({ active }: { active: SettingsTab }) {
  const { t } = useTranslation("settings")
  const navigate = useNavigate()
  return (
    <div className="flex w-44 flex-none flex-col gap-0.5">
      {SETTINGS_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => navigate(paths.settings(tab))}
          className={cn(
            "flex min-h-9 items-center rounded-full px-3.5 text-start text-sm",
            active === tab ? "bg-n300 font-medium text-ink" : "text-n800 hover:bg-hairsoft",
          )}
        >
          {t(`nav.${tab}`)}
        </button>
      ))}
    </div>
  )
}
