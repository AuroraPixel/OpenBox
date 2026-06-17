import { useCallback, useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Box, Zap, DollarSign, PanelLeftClose, PanelLeft, PanelRightClose, PanelRight, Sun, Moon, Monitor, Menu, ChevronDown, X, Bot, Cpu, Gauge } from "lucide-react"
import { useSessionStore } from "@/stores/session"
import { useUIStore } from "@/stores/ui"
import { Dropdown } from "@/components/ui/Dropdown"
import { Badge } from "@/components/ui/Badge"
import { Tooltip } from "@/components/ui/Tooltip"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

const fallbackAgentOptions = [
  { value: "build", label: "build", description: "General purpose coding agent" },
  { value: "plan", label: "plan", description: "Planning and architecture" },
  { value: "explore", label: "explore", description: "Codebase exploration" },
]

const fallbackModelOptions = [
  { value: "anthropic/claude-sonnet-4", label: "claude-sonnet" },
  { value: "anthropic/claude-opus-4", label: "claude-opus" },
  { value: "anthropic/claude-haiku", label: "claude-haiku" },
]

const defaultVariantOptions = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
]

const gpt54VariantOptions = [
  { value: "none", label: "None" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "xhigh", label: "XHigh" },
]

function getVariantOptionsForModel(modelId: string) {
  const m = modelId.toLowerCase()
  if (m.includes("gpt-5.4") || m.includes("gpt-5.2")) {
    return gpt54VariantOptions
  }
  return defaultVariantOptions
}

function getDefaultVariantForModel(modelId: string) {
  const m = modelId.toLowerCase()
  if (m.includes("gpt-5.4") || m.includes("gpt-5.2") || m.includes("gpt-5.1")) {
    return "none"
  }
  return "medium"
}

export function StatusBar() {
  const currentSessionId = useSessionStore((s) => s.currentSessionId)
  const sessions = useSessionStore((s) => s.sessions)
  const wsConnected = useUIStore((s) => s.wsConnected)
  const sidebarOpen = useUIStore((s) => s.sidebarOpen)
  const rightPanelOpen = useUIStore((s) => s.rightPanelOpen)
  const toggleSidebar = useUIStore((s) => s.toggleSidebar)
  const toggleRightPanel = useUIStore((s) => s.toggleRightPanel)

  const currentSession = sessions.find((s) => s.id === currentSessionId)
  const tokenUsage = currentSession?.token_usage

  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: api.getConfig,
    staleTime: 300000,
  })

  const { data: agents } = useQuery({
    queryKey: ["agents"],
    queryFn: api.listAgents,
    staleTime: 300000,
  })

  const agentOptions = useMemo(() => {
    if (agents && agents.length > 0) {
      return agents.map((a) => ({ value: a.name, label: a.name, description: a.description }))
    }
    return fallbackAgentOptions
  }, [agents])

  const modelOptions = useMemo(() => {
    if (config?.models && config.models.length > 0) {
      return config.models.map((m) => ({ value: m.id, label: m.name }))
    }
    return fallbackModelOptions
  }, [config])

  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const pendingModel = useUIStore((s) => s.pendingModel)
  const pendingAgent = useUIStore((s) => s.pendingAgent)
  const pendingVariant = useUIStore((s) => s.pendingVariant)
  const setPendingModel = useUIStore((s) => s.setPendingModel)
  const setPendingAgent = useUIStore((s) => s.setPendingAgent)
  const setPendingVariant = useUIStore((s) => s.setPendingVariant)

  const activeModel = currentSession?.model || pendingModel || config?.default_model || ""
  const variantOptions = useMemo(() => getVariantOptionsForModel(activeModel), [activeModel])
  const defaultVariant = useMemo(() => getDefaultVariantForModel(activeModel), [activeModel])
  const activeVariant = pendingVariant || defaultVariant

  const cycleTheme = useCallback(() => {
    const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark"
    setTheme(next)
  }, [theme, setTheme])

  const handleAgentChange = useCallback(async (agent: string) => {
    if (!currentSessionId) {
      setPendingAgent(agent)
      return
    }
    try {
      await api.updateSession(currentSessionId, { agent } as Partial<import("@/types").Session>)
      const sess = useSessionStore.getState().sessions
      const target = sess.find((s) => s.id === currentSessionId)
      if (target) {
        useSessionStore.getState().setSessions(sess.map((s) => s.id === currentSessionId ? { ...s, agent } : s))
      }
    } catch { /* ignore if backend not ready */ }
  }, [currentSessionId, setPendingAgent])

  const handleModelChange = useCallback(async (model: string) => {
    // Reset variant to the new model's default when switching models
    const newDefault = getDefaultVariantForModel(model)
    const newOptions = getVariantOptionsForModel(model)
    const currentVariant = useUIStore.getState().pendingVariant
    if (currentVariant && !newOptions.some((o) => o.value === currentVariant)) {
      setPendingVariant(newDefault)
    }

    if (!currentSessionId) {
      setPendingModel(model)
      return
    }
    try {
      await api.updateSession(currentSessionId, { model } as Partial<import("@/types").Session>)
      const sess = useSessionStore.getState().sessions
      const target = sess.find((s) => s.id === currentSessionId)
      if (target) {
        useSessionStore.getState().setSessions(sess.map((s) => s.id === currentSessionId ? { ...s, model } : s))
      }
    } catch { /* ignore if backend not ready */ }
  }, [currentSessionId, setPendingModel, setPendingVariant])

  return (
    <header className="h-12 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] flex items-center justify-between px-2 sm:px-3 shrink-0 scanlines">
      {/* Left section */}
      <div className="flex items-center gap-1.5 sm:gap-2.5 min-w-0">
        <button
          onClick={toggleSidebar}
          className="p-2 sm:p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:shadow-[0_0_6px_hsl(var(--primary)/0.2)]"
          aria-label="Toggle sidebar"
        >
          {/* Show hamburger on mobile, panel icons on desktop */}
          <span className="sm:hidden"><Menu className="h-5 w-5" /></span>
          <span className="hidden sm:inline">
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
          </span>
        </button>
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 rounded-sm bg-[hsl(var(--primary))] flex items-center justify-center shadow-[0_0_10px_hsl(var(--primary)/0.4)]">
            <Box className="h-3.5 w-3.5 text-[hsl(var(--background))]" />
          </div>
          <span className="text-sm font-display font-semibold text-[hsl(var(--foreground))] glow-cyan hidden sm:inline">OpenBox</span>
        </div>
        {currentSession && (
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-[hsl(var(--primary))]/30 font-mono hidden sm:inline">/</span>
            <span className="text-xs sm:text-sm font-mono text-[hsl(var(--muted-foreground))] truncate max-w-[100px] sm:max-w-[180px]">
              {currentSession.title || "New Chat"}
            </span>
            <SessionStatusDot status={currentSession.status} />
          </div>
        )}
      </div>

      {/* Center section — dropdowns on md+, compact chip on mobile */}
      <div className="hidden md:flex items-center gap-1.5">
        <Dropdown
          options={agentOptions}
          value={currentSession?.agent || pendingAgent || config?.default_agent || "build"}
          onChange={handleAgentChange}
          placeholder="Agent"
        />
        <Dropdown
          options={modelOptions}
          value={currentSession?.model || pendingModel || config?.default_model || "anthropic/claude-sonnet-4"}
          onChange={handleModelChange}
          placeholder="Model"
        />
        <Dropdown
          options={variantOptions}
          value={activeVariant}
          onChange={setPendingVariant}
          placeholder="Variant"
        />
      </div>
      <MobileModelChip
        model={currentSession?.model || pendingModel || config?.default_model || ""}
        agent={currentSession?.agent || pendingAgent || config?.default_agent || "build"}
        variant={activeVariant}
        modelOptions={modelOptions}
        agentOptions={agentOptions}
        variantOptions={variantOptions}
        onModelChange={handleModelChange}
        onAgentChange={handleAgentChange}
        onVariantChange={setPendingVariant}
      />

      {/* Right section */}
      <div className="flex items-center gap-1.5 sm:gap-3">
        {/* Token usage — hidden on small screens */}
        {tokenUsage && (
          <div className="hidden lg:flex items-center gap-3 text-xs text-[hsl(var(--muted-foreground))] font-mono">
            <Tooltip side="bottom" content={`Input: ${(tokenUsage.input ?? 0).toLocaleString()} | Output: ${(tokenUsage.output ?? 0).toLocaleString()} | Cache: ${(tokenUsage.cache ?? 0).toLocaleString()}`}>
              <div className="flex items-center gap-1 tabular-nums">
                <Zap className="h-3 w-3 text-[hsl(var(--accent))] glow-amber" />
                <span>{((tokenUsage.total ?? 0) / 1000).toFixed(0)}K / {((tokenUsage.limit ?? 200000) / 1000).toFixed(0)}K</span>
              </div>
            </Tooltip>
            <Tooltip side="bottom" content={`Total cost: $${(tokenUsage.cost ?? 0).toFixed(4)}`}>
              <div className="flex items-center gap-1 tabular-nums">
                <DollarSign className="h-3 w-3 text-[hsl(var(--accent))]" />
                <span>${(tokenUsage.cost ?? 0).toFixed(2)}</span>
              </div>
            </Tooltip>
          </div>
        )}
        <Tooltip side="bottom" content={`Theme: ${theme}`}>
          <button
            onClick={cycleTheme}
            className="p-2 sm:p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:shadow-[0_0_6px_hsl(var(--primary)/0.2)]"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Moon className="h-4 w-4 sm:h-3.5 sm:w-3.5" /> : theme === "light" ? <Sun className="h-4 w-4 sm:h-3.5 sm:w-3.5" /> : <Monitor className="h-4 w-4 sm:h-3.5 sm:w-3.5" />}
          </button>
        </Tooltip>
        <Tooltip side="bottom" content={wsConnected ? "Connected" : "Disconnected"}>
          <div className={cn(
            "h-2 w-2 rounded-full",
            wsConnected ? "bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success)/0.5)] animate-glow-pulse" : "bg-[hsl(var(--destructive))] shadow-[0_0_6px_hsl(var(--destructive)/0.4)]",
          )} />
        </Tooltip>
        {/* Right panel toggle — visible on all sizes */}
        <button
          onClick={toggleRightPanel}
          className="p-2 sm:p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:shadow-[0_0_6px_hsl(var(--primary)/0.2)]"
          aria-label="Toggle right panel"
        >
          {rightPanelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRight className="h-4 w-4" />}
        </button>
      </div>
    </header>
  )
}

function SessionStatusDot({ status }: { status: string }) {
  if (status === "idle") return null
  return (
    <Badge variant={status === "error" ? "error" : status === "retry" ? "warning" : "info"}>
      {status}
    </Badge>
  )
}

/**
 * Mobile model/agent selector — shows a compact chip that opens a bottom sheet.
 * Only visible below md breakpoint.
 */
function MobileModelChip({
  model, agent, variant,
  modelOptions, agentOptions, variantOptions,
  onModelChange, onAgentChange, onVariantChange,
}: {
  model: string; agent: string; variant: string
  modelOptions: { value: string; label: string }[]
  agentOptions: { value: string; label: string }[]
  variantOptions: { value: string; label: string }[]
  onModelChange: (v: string) => void
  onAgentChange: (v: string) => void
  onVariantChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const modelLabel = modelOptions.find((o) => o.value === model)?.label || model.split("/").pop() || "Model"

  return (
    <>
      {/* Compact chip — visible only on mobile */}
      <button
        onClick={() => setOpen(true)}
        className="md:hidden flex items-center gap-1 px-2 py-1 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-[10px] font-mono text-[hsl(var(--muted-foreground))] hover:border-[hsl(var(--primary))]/40 transition-colors cursor-pointer max-w-[120px]"
      >
        <Cpu className="h-3 w-3 text-[hsl(var(--primary))] shrink-0" />
        <span className="truncate">{modelLabel}</span>
        <ChevronDown className="h-3 w-3 shrink-0" />
      </button>

      {/* Bottom sheet */}
      {open && (
        <div className="md:hidden fixed inset-0 z-50 flex items-end justify-center">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <div className="relative w-full bg-[hsl(var(--card))] border-t border-[hsl(var(--border))] rounded-t-lg animate-slide-up max-h-[70vh] overflow-y-auto">
            {/* Handle */}
            <div className="flex justify-center pt-2 pb-1">
              <div className="w-10 h-1 rounded-full bg-[hsl(var(--muted-foreground))]/30" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 pb-3">
              <h3 className="text-sm font-mono uppercase tracking-wider font-semibold text-[hsl(var(--foreground))]">
                Model Settings
              </h3>
              <button onClick={() => setOpen(false)} className="p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] cursor-pointer">
                <X className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
              </button>
            </div>

            {/* Agent */}
            <div className="px-4 pb-4">
              <label className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-2">
                <Bot className="h-3 w-3" /> Agent
              </label>
              <div className="flex flex-wrap gap-1.5">
                {agentOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { onAgentChange(opt.value); }}
                    className={cn(
                      "px-3 py-2 rounded-sm text-xs font-mono transition-all cursor-pointer",
                      agent === opt.value
                        ? "bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/30"
                        : "bg-[hsl(var(--surface-1))] text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Model */}
            <div className="px-4 pb-4">
              <label className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-2">
                <Cpu className="h-3 w-3" /> Model
              </label>
              <div className="flex flex-col gap-1">
                {modelOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { onModelChange(opt.value); setOpen(false); }}
                    className={cn(
                      "w-full text-left px-3 py-2.5 rounded-sm text-xs font-mono transition-all cursor-pointer",
                      model === opt.value
                        ? "bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/30"
                        : "bg-[hsl(var(--surface-1))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Variant */}
            <div className="px-4 pb-6">
              <label className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-2">
                <Gauge className="h-3 w-3" /> Thinking
              </label>
              <div className="flex flex-wrap gap-1.5">
                {variantOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { onVariantChange(opt.value); }}
                    className={cn(
                      "px-3 py-2 rounded-sm text-xs font-mono transition-all cursor-pointer",
                      variant === opt.value
                        ? "bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/30"
                        : "bg-[hsl(var(--surface-1))] text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
