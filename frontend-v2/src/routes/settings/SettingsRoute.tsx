import { useTranslation } from "react-i18next"
import { useParams } from "react-router"
import {
  SettingsNav,
  SETTINGS_TABS,
  type SettingsTab,
  AccountPage,
  UsagePage,
  ModelsPage,
  ToolsPage,
  BrowserPage,
  AppearancePage,
} from "@/features/settings"

function ActivePage({ tab }: { tab: SettingsTab }) {
  switch (tab) {
    case "usage":
      return <UsagePage />
    case "models":
      return <ModelsPage />
    case "tools":
      return <ToolsPage />
    case "browser":
      return <BrowserPage />
    case "appearance":
      return <AppearancePage />
    default:
      return <AccountPage />
  }
}

export default function SettingsRoute() {
  const { t } = useTranslation("settings")
  const { tab } = useParams()
  const active: SettingsTab = SETTINGS_TABS.includes(tab as SettingsTab) ? (tab as SettingsTab) : "account"

  return (
    <div className="scr min-h-0 flex-1 overflow-auto px-6.5 pt-1.5 pb-7">
      <div className="mx-auto flex w-full max-w-[860px] items-start gap-7">
        <SettingsNav active={active} />
        <div className="flex min-w-0 flex-1 flex-col gap-4.5">
          <div className="flex flex-col gap-1">
            <span className="text-2xl font-medium tracking-tight">{t(`nav.${active}`)}</span>
            <span className="text-sm text-n600">{t(`hint.${active}`)}</span>
          </div>
          <ActivePage tab={active} />
        </div>
      </div>
    </div>
  )
}
