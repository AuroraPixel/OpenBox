import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import {
  useBrowserStatus,
  useUpdateBrowserPreference,
  type BrowserMode,
} from "@/features/settings/api/browser"

const MODES: BrowserMode[] = ["auto", "local", "remote"]

/** One selectable browser-mode card: title + one-line explanation. */
function ModeCard({
  mode,
  active,
  onPick,
}: {
  mode: BrowserMode
  active: boolean
  onPick: () => void
}) {
  const { t } = useTranslation("settings")
  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={active}
      className={cn(
        "flex flex-col gap-1 rounded-lg border bg-card px-4 py-3.5 text-start",
        active ? "border-ink" : "border-hair",
      )}
    >
      <span className="text-base">{t(`browser.mode.${mode}`)}</span>
      <span className="text-pretty text-xs text-n600">{t(`browser.desc.${mode}`)}</span>
    </button>
  )
}

/** Live line: is the user's own browser connected, is the cloud one available. */
function StatusLine({ remote, local }: { remote: boolean; local: boolean }) {
  const { t } = useTranslation("settings")
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-hair bg-card px-4 py-3.5">
      <span className="text-xs text-n600">{t("browser.status.title")}</span>
      <div className="flex flex-col gap-1 text-sm text-n700">
        <span>
          {t("browser.status.remote")} ·{" "}
          {remote ? t("browser.status.connected") : t("browser.status.disconnected")}
        </span>
        <span>
          {t("browser.status.local")} ·{" "}
          {local ? t("browser.status.available") : t("browser.status.unavailable")}
        </span>
      </div>
    </div>
  )
}

export function BrowserPage() {
  const { t } = useTranslation("settings")
  const status = useBrowserStatus()
  const update = useUpdateBrowserPreference()

  const preference = status.data?.preference ?? "auto"
  const remoteConnected = status.data?.remote.connected ?? false
  const localAvailable = status.data?.local.available ?? false

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2.5">
        {MODES.map((mode) => (
          <ModeCard
            key={mode}
            mode={mode}
            active={preference === mode}
            onPick={() => update.mutate(mode)}
          />
        ))}
      </div>

      <StatusLine remote={remoteConnected} local={localAvailable} />

      {preference === "remote" && !remoteConnected && (
        <span className="text-pretty text-xs text-n600">{t("browser.fallbackHint")}</span>
      )}
    </div>
  )
}
