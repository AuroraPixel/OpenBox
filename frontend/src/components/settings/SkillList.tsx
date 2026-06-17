import { useState } from "react"
import { Box, Container, FileCode, Folder, Globe, Plus, Shield, Trash2, Zap } from "lucide-react"
import { InstallSkillDialog } from "@/components/settings/InstallSkillDialog"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useToast } from "@/components/ui/Toast"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"
import type { SkillInfo } from "@/types"

interface SkillListProps {
  skills: SkillInfo[]
  onRefresh: () => void
}

const sourceConfig: Record<string, { label: string; icon: React.ReactNode; color: string; bgColor: string }> = {
  builtin: {
    label: "System",
    icon: <Shield className="h-3 w-3" />,
    color: "text-[hsl(var(--primary))]",
    bgColor: "bg-[hsl(var(--primary))]/10",
  },
  container: {
    label: "User",
    icon: <Container className="h-3 w-3" />,
    color: "text-[hsl(var(--success))]",
    bgColor: "bg-[hsl(var(--success))]/10",
  },
  global: {
    label: "Global",
    icon: <Globe className="h-3 w-3" />,
    color: "text-[hsl(var(--accent))]",
    bgColor: "bg-[hsl(var(--accent))]/10",
  },
  project: {
    label: "Project",
    icon: <Folder className="h-3 w-3" />,
    color: "text-violet-400",
    bgColor: "bg-violet-500/10",
  },
  remote: {
    label: "Remote",
    icon: <Box className="h-3 w-3" />,
    color: "text-orange-400",
    bgColor: "bg-orange-500/10",
  },
}

export function SkillList({ skills, onRefresh }: SkillListProps) {
  const [installOpen, setInstallOpen] = useState(false)
  const [confirmTarget, setConfirmTarget] = useState<string | null>(null)
  const { addToast } = useToast()

  const handleUninstall = async () => {
    if (!confirmTarget) return
    const name = confirmTarget
    setConfirmTarget(null)
    try {
      await api.uninstallSkill(name)
      addToast("success", `Skill "${name}" uninstalled`)
      onRefresh()
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : `Failed to uninstall "${name}"`)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-display uppercase tracking-wider text-[hsl(var(--foreground))]">Skills</h2>
          <p className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mt-0.5">
            {skills.length} skill{skills.length !== 1 ? "s" : ""} installed
          </p>
        </div>
        <button
          onClick={() => setInstallOpen(true)}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
            "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
            "hover:opacity-90 glow-cyan",
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          Install Skill
        </button>
      </div>

      <div className="grid gap-3">
        {skills.map((skill) => {
          const source = sourceConfig[skill.source] || sourceConfig.global
          return (
            <div
              key={skill.name}
              className={cn(
                "rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4",
                "hover:border-[hsl(var(--primary))]/40 transition-colors",
                "group",
              )}
            >
              <div className="flex items-start gap-3">
                {/* Icon */}
                <div className="h-10 w-10 rounded-sm bg-[hsl(var(--accent))]/10 flex items-center justify-center shrink-0 glow-amber">
                  <Zap className="h-5 w-5 text-[hsl(var(--accent))]" />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-display text-sm uppercase tracking-wider">{skill.name}</span>
                    <span className={cn(
                      "inline-flex items-center gap-1 px-2 py-0.5 rounded-sm text-[10px] font-mono uppercase tracking-wider",
                      source.bgColor, source.color,
                    )}>
                      {source.icon}
                      {source.label}
                    </span>
                  </div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] leading-relaxed">
                    {skill.description}
                  </p>
                  {skill.files && skill.files.length > 0 && (
                    <div className="flex items-center gap-1.5 mt-2 text-[11px] text-[hsl(var(--muted-foreground))]/70">
                      <FileCode className="h-3 w-3" />
                      <span className="font-mono">
                        {skill.files.slice(0, 3).join(", ")}{skill.files.length > 3 ? ` +${skill.files.length - 3} more` : ""}
                      </span>
                    </div>
                  )}
                </div>

                {/* Actions */}
                {skill.source !== "global" && skill.source !== "project" && (
                  <button
                    onClick={() => setConfirmTarget(skill.name)}
                    className={cn(
                      "p-2 rounded-sm transition-all cursor-pointer shrink-0",
                      "text-[hsl(var(--muted-foreground))] opacity-0 group-hover:opacity-100",
                      "hover:text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10",
                    )}
                    title="Uninstall skill"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>
          )
        })}

        {skills.length === 0 && (
          <div className="rounded-sm border border-dashed border-[hsl(var(--border))] p-10 text-center grid-pattern">
            <Zap className="h-8 w-8 mx-auto mb-3 text-[hsl(var(--muted-foreground))]/40" />
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No skills installed</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1">
              Click "Install Skill" to add custom capabilities to your agent.
            </p>
          </div>
        )}
      </div>

      <InstallSkillDialog
        open={installOpen}
        onClose={() => setInstallOpen(false)}
        onInstalled={onRefresh}
      />

      <ConfirmDialog
        open={!!confirmTarget}
        title="Uninstall Skill"
        message={`Are you sure you want to uninstall "${confirmTarget}"? This action cannot be undone.`}
        confirmLabel="Uninstall"
        variant="danger"
        onConfirm={handleUninstall}
        onCancel={() => setConfirmTarget(null)}
      />
    </div>
  )
}
