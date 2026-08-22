// Which agent the conversation runs as — build, plan, or one the user
// defined.
//
// Plan mode had no way in from the UI at all: the only route was the model
// deciding to call plan_enter. That made a whole mode of the product reachable
// only by asking for it in prose, and there was nothing on screen to say which
// mode you were already in.
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, ChevronDown } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import type { ChatAgent } from "../../api/agents"

interface Props {
  agents: ChatAgent[]
  /** The agent this conversation is on; falls back to build. */
  activeId: string
  onPick?: (name: string) => void
  /** A run is in flight — switching mid-turn would not apply to it. */
  disabled?: boolean
}

/** Translated text for the built-ins, falling through to what the server sent
 *  for anything the user defined — those names and descriptions are theirs and
 *  cannot be translated here. */
function useAgentText() {
  const { t } = useTranslation("chat")
  const lookup = (key: string, fallback?: string) => {
    const translated = t(key)
    return translated === key ? fallback : translated
  }
  return {
    label: (name: string) => lookup(`mode.${name}`, name) ?? name,
    describe: (a: ChatAgent) => lookup(`mode.${a.name}Desc`, a.description),
  }
}

export function ModePicker({ agents, activeId, onPick, disabled }: Props) {
  const { t } = useTranslation("chat")
  const [open, setOpen] = useState(false)
  const { label, describe } = useAgentText()

  // One choice is not a choice. A deployment that disabled plan should not
  // show a picker that cannot pick anything.
  if (agents.length < 2) return null

  const active = agents.find((a) => a.name === activeId) ?? agents[0]

  return (
    <div className="relative flex-none">
      <Menu open={open} onClose={() => setOpen(false)} className="start-0 bottom-10 w-60">
        {agents.map((agent) => (
          <MenuItem key={agent.name} onClick={() => { onPick?.(agent.name); setOpen(false) }}>
            <span className="flex items-start gap-2">
              <Check
                className={cn(
                  "mt-0.5 size-3.5 flex-none",
                  agent.name === active.name ? "text-ink" : "opacity-0",
                )}
              />
              <span className="min-w-0">
                <span className="block">{label(agent.name)}</span>
                {describe(agent) && (
                  <span className="text-n600 mt-0.5 block text-xs leading-4">
                    {describe(agent)}
                  </span>
                )}
              </span>
            </span>
          </MenuItem>
        ))}
      </Menu>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        title={t("mode.label")}
        aria-label={t("mode.label")}
        className={cn(
          "text-n600 hover:bg-hairsoft hover:text-ink flex h-8 items-center gap-1 rounded-full px-2.5 text-sm transition-colors disabled:opacity-40",
          // Plan mode changes what the agent is allowed to do, so it says so
          // rather than sitting in the same grey as everything else.
          active.name === "plan" && "text-a700",
        )}
      >
        <span
          className={cn(
            "size-1.5 flex-none rounded-full",
            active.name === "plan" ? "bg-accent" : "bg-n500",
          )}
          style={active.color ? { background: active.color } : undefined}
        />
        {label(active.name)}
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
      </button>
    </div>
  )
}
