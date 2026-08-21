import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import { useAgentConfig, useAgents, usePreferences, useUpdatePreferences } from "@/features/settings/api/settings"
import { RowCard, Row, ValuePill } from "./SettingsRow"

interface Option {
  id: string
  label: string
}

function MenuPicker({ value, options, onPick }: { value: string; options: Option[]; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative flex-none">
      <ValuePill value={value} onClick={() => setOpen((o) => !o)} />
      <Menu open={open} onClose={() => setOpen(false)} className="end-0 top-9 max-h-64 min-w-44 overflow-auto">
        {options.map((o) => (
          <MenuItem
            key={o.id}
            onClick={() => {
              onPick(o.id)
              setOpen(false)
            }}
          >
            {o.label}
          </MenuItem>
        ))}
      </Menu>
    </div>
  )
}

const DASH = "—"

export function ModelsPage() {
  const { t } = useTranslation("settings")
  const config = useAgentConfig()
  const agents = useAgents()
  const prefs = usePreferences()
  const update = useUpdatePreferences()

  const models = config.data?.models ?? []
  const agentList = agents.data ?? []
  const curModelId = prefs.data?.default_model ?? config.data?.default_model
  const curAgentName = prefs.data?.default_agent ?? config.data?.default_agent
  const modelName = models.find((m) => m.id === curModelId)?.name ?? curModelId ?? DASH
  const agentName = agentList.find((a) => a.name === curAgentName)?.name ?? curAgentName ?? DASH

  return (
    <RowCard>
      <Row
        label={t("models.defaultModel")}
        hint={t("models.defaultModelHint")}
        right={
          <MenuPicker
            value={modelName}
            options={models.map((m) => ({ id: m.id, label: m.name }))}
            onPick={(id) => update.mutate({ default_model: id })}
          />
        }
      />
      <Row
        label={t("models.defaultAgent")}
        hint={t("models.defaultAgentHint")}
        right={
          <MenuPicker
            value={agentName}
            options={agentList.map((a) => ({ id: a.name, label: a.name }))}
            onPick={(name) => update.mutate({ default_agent: name })}
          />
        }
      />
    </RowCard>
  )
}
