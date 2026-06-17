import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Bot, ChevronDown, Clock, Server, Settings, Zap } from "lucide-react"
import { AgentConfig } from "@/components/settings/AgentConfig"
import { McpManager } from "@/components/settings/McpManager"
import { SkillList } from "@/components/settings/SkillList"
import { CronJobList } from "@/components/cron/CronJobList"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface SettingsPageProps {
  sub?: string
}

const settingsTabs = [
  { id: "agents", label: "Agents", icon: Bot, description: "Configure AI agent models and tools" },
  { id: "skills", label: "Skills", icon: Zap, description: "Install and manage agent skills" },
  { id: "mcp", label: "MCP Servers", icon: Server, description: "Connect external tool servers" },
  { id: "cron", label: "Cron Jobs", icon: Clock, description: "Manage scheduled tasks across all sessions" },
]

export function SettingsPage({ sub }: SettingsPageProps) {
  const [activeTab, setActiveTab] = useState(sub || "agents")
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const { data: agents = [] } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
  })

  const { data: skills = [], refetch: refetchSkills } = useQuery({
    queryKey: ["skills"],
    queryFn: api.listSkills,
  })

  const { data: mcpServers = [], refetch: refetchMcp } = useQuery({
    queryKey: ["mcp"],
    queryFn: api.getMcpStatus,
  })

  const currentTab = settingsTabs.find((t) => t.id === activeTab) || settingsTabs[0]

  return (
    <div className="h-full overflow-y-auto bg-[hsl(var(--background))] grid-pattern">
      <div className="max-w-5xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        {/* Header */}
        <div className="mb-5 sm:mb-8">
          <div className="flex items-center gap-3 mb-1">
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 flex items-center justify-center shadow-[0_0_10px_hsl(var(--primary)/0.2)]">
              <Settings className="h-5 w-5 text-[hsl(var(--primary))] glow-cyan" />
            </div>
            <h1 className="text-xl font-display font-bold text-[hsl(var(--foreground))]">Settings</h1>
          </div>
          <p className="text-sm text-[hsl(var(--muted-foreground))] ml-12 font-mono hidden sm:block">
            Manage your agents, skills, and MCP server connections.
          </p>
        </div>

        {/* Mobile: Custom dropdown */}
        <div className="sm:hidden mb-4 relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] cursor-pointer hover:border-[hsl(var(--primary))]/40 transition-colors"
          >
            {(() => { const Icon = currentTab.icon; return <Icon className="h-4 w-4 text-[hsl(var(--primary))]" /> })()}
            <span className="flex-1 text-left text-sm font-mono uppercase tracking-wider text-[hsl(var(--foreground))]">
              {currentTab.label}
            </span>
            <ChevronDown className={cn("h-4 w-4 text-[hsl(var(--muted-foreground))] transition-transform", dropdownOpen && "rotate-180")} />
          </button>

          {dropdownOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setDropdownOpen(false)} />
              <div className="absolute left-0 right-0 top-full mt-1 z-50 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-xl overflow-hidden animate-slide-up">
                {settingsTabs.map((tab) => {
                  const Icon = tab.icon
                  const isActive = tab.id === activeTab
                  return (
                    <button
                      key={tab.id}
                      onClick={() => { setActiveTab(tab.id); setDropdownOpen(false) }}
                      className={cn(
                        "w-full flex items-center gap-3 px-4 py-3 text-left transition-colors cursor-pointer",
                        isActive
                          ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))]"
                          : "text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]/60",
                      )}
                    >
                      <Icon className={cn("h-4 w-4", isActive ? "text-[hsl(var(--primary))]" : "text-[hsl(var(--muted-foreground))]")} />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-mono uppercase tracking-wider">{tab.label}</span>
                        <p className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono mt-0.5">{tab.description}</p>
                      </div>
                      {isActive && <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--primary))] shrink-0" />}
                    </button>
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* Desktop: Pill tabs */}
        <div className="hidden sm:block mb-8">
          <div className="flex gap-1 p-1 rounded-sm bg-[hsl(var(--muted))]/30 border border-[hsl(var(--border))]/30 w-fit">
            {settingsTabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-sm text-sm font-medium transition-all cursor-pointer",
                    activeTab === tab.id
                      ? "bg-[hsl(var(--card))] text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/20 shadow-[0_0_8px_hsl(var(--primary)/0.1)]"
                      : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] border border-transparent",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="font-mono uppercase tracking-wider text-xs">{tab.label}</span>
                </button>
              )
            })}
          </div>
          <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono mt-4">
            {currentTab.description}
          </p>
        </div>

        {/* Content */}
        {activeTab === "agents" && <AgentConfig agents={agents} />}
        {activeTab === "skills" && <SkillList skills={skills} onRefresh={() => refetchSkills()} />}
        {activeTab === "mcp" && <McpManager servers={mcpServers} onRefresh={() => refetchMcp()} />}
        {activeTab === "cron" && <CronJobList showSessionInfo />}
      </div>
    </div>
  )
}
