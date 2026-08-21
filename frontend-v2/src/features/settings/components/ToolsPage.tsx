import { useTranslation } from "react-i18next"
import { useSkills, useMcpServers } from "@/features/settings/api/settings"
import { RowCard, Row } from "./SettingsRow"

export function ToolsPage() {
  const { t } = useTranslation("settings")
  const skills = useSkills()
  const mcp = useMcpServers()

  const skillCount = skills.data?.length ?? 0
  const servers = mcp.data ?? []
  const names = servers
    .map((s) => s.name)
    .filter((n): n is string => Boolean(n))
    .join(" · ")

  return (
    <RowCard>
      <Row label={t("tools.skills")} hint={t("tools.skillsHint", { count: skillCount })} />
      <Row
        label={t("tools.mcp")}
        hint={servers.length ? t("tools.mcpHint", { count: servers.length }) : t("tools.mcpNone")}
        right={
          names ? <span className="max-w-[40%] flex-none truncate text-2xs text-n500">{names}</span> : undefined
        }
      />
      <div className="border-t border-hair px-5 py-3.5 text-pretty text-xs text-n600">
        {t("tools.permissionNote")}
      </div>
    </RowCard>
  )
}
