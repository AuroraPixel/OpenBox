import { useState, useCallback } from "react"
import { AlertCircle, BookOpen, ChevronDown, ChevronRight, ExternalLink, FileText, Key, Loader2, Plug, Plus, RefreshCw, Server, Trash2, Unplug, Wrench } from "lucide-react"
import { AddMcpServerDialog } from "@/components/settings/AddMcpServerDialog"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useToast } from "@/components/ui/Toast"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"
import type { McpServer } from "@/types"

interface McpManagerProps {
  servers: McpServer[]
  onRefresh: () => void
}

const statusConfig: Record<string, { color: string; bgColor: string; dotColor: string; glow: string }> = {
  connected: { color: "text-[hsl(var(--success))]", bgColor: "bg-[hsl(var(--success))]/10", dotColor: "bg-[hsl(var(--success))]", glow: "glow-green" },
  disconnected: { color: "text-[hsl(var(--muted-foreground))]", bgColor: "bg-[hsl(var(--muted))]", dotColor: "bg-[hsl(var(--muted-foreground))]", glow: "" },
  error: { color: "text-[hsl(var(--destructive))]", bgColor: "bg-[hsl(var(--destructive))]/10", dotColor: "bg-[hsl(var(--destructive))]", glow: "glow-coral" },
}

// Popular MCP servers for quick install
const POPULAR_SERVERS = [
  { name: "filesystem", type: "stdio" as const, command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"], description: "Read/write files in the workspace" },
  { name: "github", type: "stdio" as const, command: "npx", args: ["-y", "@modelcontextprotocol/server-github"], description: "GitHub repos, issues, PRs", env: { GITHUB_PERSONAL_ACCESS_TOKEN: "" } },
  { name: "postgres", type: "stdio" as const, command: "npx", args: ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"], description: "Query PostgreSQL databases" },
  { name: "memory", type: "stdio" as const, command: "npx", args: ["-y", "@modelcontextprotocol/server-memory"], description: "Persistent knowledge graph memory" },
]

export function McpManager({ servers, onRefresh }: McpManagerProps) {
  const [addOpen, setAddOpen] = useState(false)
  const [loadingAction, setLoadingAction] = useState<string | null>(null) // "connect:name", "disconnect:name", etc.
  const [actionError, setActionError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set()) // which server cards are expanded

  const toggleExpand = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const withLoading = useCallback(async (key: string, fn: () => Promise<void>) => {
    setLoadingAction(key)
    setActionError(null)
    try {
      await fn()
      onRefresh()
    } catch (e: any) {
      setActionError(e?.message || "Operation failed")
    } finally {
      setLoadingAction(null)
    }
  }, [onRefresh])

  const handleConnect = (name: string) => withLoading(`connect:${name}`, () => api.connectMcp(name))
  const handleDisconnect = (name: string) => withLoading(`disconnect:${name}`, () => api.disconnectMcp(name))
  const handleRefresh = (name: string) => withLoading(`refresh:${name}`, () => api.refreshMcp(name).then(() => {}))

  const handleOAuth = async (name: string) => {
    setLoadingAction(`oauth:${name}`)
    setActionError(null)
    try {
      const { authorize_url } = await api.startMcpOAuth(name)
      window.open(authorize_url, "_blank", "width=600,height=700")
    } catch (e: any) {
      setActionError(e?.message || "OAuth failed")
    } finally {
      setLoadingAction(null)
    }
  }

  const [removeTarget, setRemoveTarget] = useState<{ name: string; status: string } | null>(null)
  const { addToast } = useToast()

  const handleRemove = async () => {
    if (!removeTarget) return
    const { name, status } = removeTarget
    setRemoveTarget(null)
    try {
      await withLoading(`remove:${name}`, async () => {
        if (status === "connected") await api.disconnectMcp(name)
        await api.removeMcpServer(name)
      })
      addToast("success", `MCP server "${name}" removed`)
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : `Failed to remove "${name}"`)
    }
  }

  const handleQuickInstall = async (preset: typeof POPULAR_SERVERS[0]) => {
    // Check if already installed
    if (servers.some((s) => s.name === preset.name)) {
      setActionError(`Server "${preset.name}" already exists`)
      return
    }
    await withLoading(`install:${preset.name}`, async () => {
      await api.addMcpServer({
        name: preset.name,
        type: preset.type,
        command: preset.command,
        args: preset.args,
        env: preset.env,
      })
      try { await api.connectMcp(preset.name) } catch {}
    })
  }

  const isLoading = (key: string) => loadingAction === key

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-display uppercase tracking-wider text-[hsl(var(--foreground))]">MCP Servers</h2>
          <p className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mt-0.5">
            Extend the agent with external tools, data sources, and APIs
          </p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
            "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
            "hover:opacity-90 glow-cyan",
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          Add Server
        </button>
      </div>

      {/* Action error toast */}
      {actionError && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] font-mono glow-coral animate-slide-up">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1">{actionError}</span>
          <button onClick={() => setActionError(null)} className="text-[hsl(var(--destructive))] hover:opacity-70 cursor-pointer px-1">x</button>
        </div>
      )}

      {/* Connected count */}
      {servers.length > 0 && (
        <p className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
          {servers.filter((s) => s.status === "connected").length} of {servers.length} connected
        </p>
      )}

      {/* Server cards */}
      <div className="grid gap-3">
        {servers.map((server) => {
          const st = statusConfig[server.status] || statusConfig.disconnected
          const isExpanded = expanded.has(server.name)
          const toolCount = server.tools.length
          const resourceCount = server.resources?.length ?? 0
          const promptCount = server.prompts?.length ?? 0
          return (
            <div
              key={server.name}
              className={cn(
                "rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden",
                "hover:border-[hsl(var(--primary))]/40 transition-colors",
                "group",
              )}
            >
              {/* Compact header — always visible, clickable to expand */}
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  onClick={() => toggleExpand(server.name)}
                  className="shrink-0 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] cursor-pointer"
                >
                  {isExpanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                </button>
                <div className={cn(
                  "h-8 w-8 rounded-sm flex items-center justify-center shrink-0",
                  server.status === "connected"
                    ? "bg-[hsl(var(--success))]/10"
                    : server.status === "error"
                      ? "bg-[hsl(var(--destructive))]/10"
                      : "bg-[hsl(var(--muted))]",
                )}>
                  <Server className={cn("h-4 w-4", st.color)} />
                </div>
                <div className="flex-1 min-w-0 cursor-pointer" onClick={() => toggleExpand(server.name)}>
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-sm uppercase tracking-wider">{server.name}</h3>
                    <span className={cn(
                      "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[10px] font-mono uppercase tracking-wider",
                      st.bgColor, st.color,
                    )}>
                      <span className={cn("h-1.5 w-1.5 rounded-full", st.dotColor)} />
                      {isLoading(`connect:${server.name}`) ? "connecting..." : isLoading(`disconnect:${server.name}`) ? "disconnecting..." : server.status}
                    </span>
                    <span className="text-[10px] text-[hsl(var(--muted-foreground))]/60 font-mono">{server.type}</span>
                    {/* Inline counts when collapsed */}
                    {!isExpanded && server.status === "connected" && (toolCount > 0 || resourceCount > 0) && (
                      <span className="text-[10px] text-[hsl(var(--muted-foreground))]/50 font-mono">
                        {[
                          toolCount > 0 ? `${toolCount} tools` : "",
                          resourceCount > 0 ? `${resourceCount} res` : "",
                          promptCount > 0 ? `${promptCount} prompts` : "",
                        ].filter(Boolean).join(" · ")}
                      </span>
                    )}
                    {!isExpanded && server.error && (
                      <AlertCircle className="h-3 w-3 text-[hsl(var(--destructive))]" />
                    )}
                  </div>
                </div>

                {/* Actions — always visible */}
                <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                  {server.status === "connected" ? (
                    <>
                      <button onClick={() => handleRefresh(server.name)} disabled={!!loadingAction} className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10 disabled:opacity-50 cursor-pointer transition-all" title="Refresh">
                        <RefreshCw className={cn("h-3.5 w-3.5", isLoading(`refresh:${server.name}`) && "animate-spin")} />
                      </button>
                      <button onClick={() => handleDisconnect(server.name)} disabled={!!loadingAction} className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/10 disabled:opacity-50 cursor-pointer transition-all" title="Disconnect">
                        {isLoading(`disconnect:${server.name}`) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
                      </button>
                    </>
                  ) : (
                    <>
                      {server.type === "remote" && server.status === "error" && (
                        <button onClick={() => handleOAuth(server.name)} disabled={!!loadingAction} className="p-1.5 rounded-sm text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/10 disabled:opacity-50 cursor-pointer transition-all" title="OAuth">
                          {isLoading(`oauth:${server.name}`) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Key className="h-3.5 w-3.5" />}
                        </button>
                      )}
                      <button onClick={() => handleConnect(server.name)} disabled={!!loadingAction} className="p-1.5 rounded-sm text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10 disabled:opacity-50 cursor-pointer transition-all" title="Connect">
                        {isLoading(`connect:${server.name}`) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plug className="h-3.5 w-3.5" />}
                      </button>
                    </>
                  )}
                  <button onClick={() => setRemoveTarget({ name: server.name, status: server.status })} disabled={!!loadingAction} className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] opacity-0 group-hover:opacity-100 hover:text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 disabled:opacity-50 cursor-pointer transition-all" title="Remove">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {/* Expanded detail section */}
              {isExpanded && (
                <div className="px-4 pb-4 pt-0 space-y-3 border-t border-[hsl(var(--border))]/30 animate-fade-in">
                  {/* URL / command */}
                  <div className="pt-3">
                    {server.url && <p className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]/60 truncate">{server.url}</p>}
                    {server.command && <p className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]/60 truncate">{server.command} {(server.args || []).join(" ")}</p>}
                  </div>

                  {/* Error */}
                  {server.error && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] glow-coral">
                      <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                      <span className="font-mono">{server.error}</span>
                    </div>
                  )}

                  {/* Tools / Resources / Prompts */}
                  {server.status === "connected" && (
                    <div className="space-y-2">
                      {toolCount > 0 && (
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))] uppercase tracking-wider font-mono">
                            <Wrench className="h-3 w-3" />
                            <span>{toolCount} tools</span>
                          </div>
                          <div className="flex flex-wrap gap-1.5">
                            {server.tools.map((t) => (
                              <span key={t.name} title={t.description} className="inline-flex items-center px-2 py-0.5 rounded-sm text-[11px] font-mono bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] border border-[hsl(var(--border))] cursor-default">
                                {t.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {resourceCount > 0 && (
                        <div className="flex items-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))] uppercase tracking-wider font-mono">
                          <FileText className="h-3 w-3" />
                          <span>{resourceCount} resources</span>
                        </div>
                      )}
                      {promptCount > 0 && (
                        <div className="flex items-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))] uppercase tracking-wider font-mono">
                          <BookOpen className="h-3 w-3" />
                          <span>{promptCount} prompts</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Quick Install section — shown when fewer than 3 servers */}
      {servers.length < 3 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-px flex-1 bg-[hsl(var(--border))]/50" />
            <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]/60">Quick Install</span>
            <div className="h-px flex-1 bg-[hsl(var(--border))]/50" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {POPULAR_SERVERS.filter((p) => !servers.some((s) => s.name === p.name)).map((preset) => (
              <button
                key={preset.name}
                onClick={() => handleQuickInstall(preset)}
                disabled={!!loadingAction}
                className={cn(
                  "flex items-center gap-3 p-3 rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]/50",
                  "hover:bg-[hsl(var(--primary))]/5 hover:border-[hsl(var(--primary))]/20 transition-all cursor-pointer text-left",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "group/preset",
                )}
              >
                <div className="h-8 w-8 rounded-sm bg-[hsl(var(--muted))]/50 flex items-center justify-center shrink-0 group-hover/preset:bg-[hsl(var(--primary))]/10">
                  <Server className="h-4 w-4 text-[hsl(var(--muted-foreground))] group-hover/preset:text-[hsl(var(--primary))]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-mono font-medium">{preset.name}</div>
                  <div className="text-[10px] text-[hsl(var(--muted-foreground))]/60 truncate">{preset.description}</div>
                </div>
                {isLoading(`install:${preset.name}`) ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[hsl(var(--primary))] shrink-0" />
                ) : (
                  <Plus className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))] opacity-0 group-hover/preset:opacity-100 shrink-0" />
                )}
              </button>
            ))}
          </div>
          <a
            href="https://github.com/modelcontextprotocol/servers"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--primary))] hover:underline cursor-pointer"
          >
            <ExternalLink className="h-3 w-3" />
            Browse more MCP servers
          </a>
        </div>
      )}

      {/* Empty state */}
      {servers.length === 0 && (
        <div className="rounded-sm border border-dashed border-[hsl(var(--border))] p-8 text-center grid-pattern">
          <Server className="h-8 w-8 mx-auto mb-3 text-[hsl(var(--muted-foreground))]/40" />
          <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No MCP servers configured</p>
          <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1.5 max-w-sm mx-auto leading-relaxed">
            MCP (Model Context Protocol) servers extend the AI agent with external tools, data sources, and APIs.
            Use Quick Install above or click "Add Server" for custom configuration.
          </p>
        </div>
      )}

      <AddMcpServerDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onAdded={onRefresh}
      />

      <ConfirmDialog
        open={!!removeTarget}
        title="Remove MCP Server"
        message={`Are you sure you want to remove "${removeTarget?.name}"? The server will be disconnected and its configuration deleted.`}
        confirmLabel="Remove"
        variant="danger"
        onConfirm={handleRemove}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  )
}
