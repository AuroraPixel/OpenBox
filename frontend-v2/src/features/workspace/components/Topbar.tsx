import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useParams } from "react-router"
import { PanelLeft, PanelRight, Upload } from "lucide-react"
import { useCopy } from "@/shared/hooks/useCopy"
import { formatTokens } from "@/shared/lib/format"
import { toast } from "@/shared/ui/Toast"
import { useWorkspaceUi } from "../stores/ui"
import { useProjectsQuery } from "../api/projects"
import { useSessionsQuery } from "../api/sessions"

interface TopbarProps {
  panelOpen: boolean
  onTogglePanel: () => void
}

export function Topbar({ panelOpen, onTogglePanel }: TopbarProps) {
  const { t } = useTranslation("workspace")
  const { sessionId } = useParams()
  const location = useLocation()
  const collapsed = useWorkspaceUi((s) => s.sidebarCollapsed)
  const toggleSidebar = useWorkspaceUi((s) => s.toggleSidebar)
  const sessions = useSessionsQuery()
  const projects = useProjectsQuery()
  const { copy } = useCopy()

  const isSettings = location.pathname.includes("/settings")
  const session = useMemo(
    () => (sessions.data ?? []).find((s) => s.id === sessionId) ?? null,
    [sessions.data, sessionId],
  )
  const project = useMemo(
    () => (projects.data ?? []).find((p) => p.id === session?.project_id) ?? null,
    [projects.data, session],
  )

  const title = isSettings ? t("settings") : (session?.title ?? t("untitledChat"))
  const subtitle = isSettings
    ? t("settings:subtitle", { ns: "settings" })
    : (project?.name ?? t("unsorted"))
  const contextTokens = session?.token_usage?.context ?? 0

  const share = () => {
    copy(window.location.href)
    toast("info", t("shareCopied"))
  }

  return (
    <div className="flex h-15.5 flex-none items-center gap-3 ps-6.5 pe-4.5">
      {collapsed && (
        <button
          type="button"
          className="flex size-8 flex-none items-center justify-center rounded-full text-n700 hover:bg-n200"
          onClick={toggleSidebar}
          title={t("expand")}
          aria-label={t("expand")}
        >
          <PanelLeft size={17} strokeWidth={2.4} />
        </button>
      )}
      <div className="flex min-w-0 flex-1 items-baseline gap-2.5 overflow-hidden">
        <span className="max-w-3/5 flex-none truncate text-lg font-medium">{title}</span>
        <span className="min-w-0 flex-none truncate text-sm text-n600">{subtitle}</span>
      </div>
      {session && contextTokens > 0 && (
        <span className="flex-none text-sm whitespace-nowrap text-n600">
          {t("ctxTokens", { tokens: formatTokens(contextTokens) })}
        </span>
      )}
      {session && (
        <button
          type="button"
          className="flex size-8 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
          title={t("share")}
          aria-label={t("share")}
          onClick={share}
        >
          <Upload size={16} strokeWidth={2.4} />
        </button>
      )}
      {!panelOpen && !isSettings && (
        <button
          type="button"
          className="flex size-8 flex-none items-center justify-center rounded-full text-n700 hover:bg-n200"
          onClick={onTogglePanel}
          title={t("openPanel")}
          aria-label={t("openPanel")}
        >
          <PanelRight size={17} strokeWidth={2.4} />
        </button>
      )}
    </div>
  )
}
