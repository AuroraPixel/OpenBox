import { useState, useMemo, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { MonitorSmartphone, Power, PowerOff, AlertCircle, Wifi, WifiOff, Download, X, Monitor } from "lucide-react"
import { api } from "@/services/api"
import { Spinner } from "@/components/ui/Spinner"

interface DevBrowserPanelProps {
  sessionId: string
}

type PanelState = "idle" | "confirm" | "starting" | "running" | "error"

export function DevBrowserPanel({ sessionId }: DevBrowserPanelProps) {
  const queryClient = useQueryClient()
  const [panelState, setPanelState] = useState<PanelState>("idle")
  const [bannerDismissed, setBannerDismissed] = useState(false)

  // Get session's container
  const { data: sandboxData, isLoading: sandboxLoading } = useQuery({
    queryKey: ["session-sandbox", sessionId],
    queryFn: () => api.getSessionSandbox(sessionId),
    refetchInterval: 5000,
  })

  const { data: containerData, isLoading: containersLoading } = useQuery({
    queryKey: ["containers"],
    queryFn: api.listContainers,
    refetchInterval: 5000,
    enabled: !sandboxData?.available,
  })

  const containerId = useMemo(() => {
    if (sandboxData?.available && sandboxData.container_id) {
      return sandboxData.container_id
    }
    return containerData?.containers?.find((c) => c.status === "running")?.id || null
  }, [sandboxData, containerData])

  // Poll dev-browser status when running
  const { data: statusData } = useQuery({
    queryKey: ["dev-browser-status", containerId],
    queryFn: () => containerId ? api.getDevBrowserStatus(containerId) : Promise.resolve(null),
    enabled: !!containerId && (panelState === "running" || panelState === "starting"),
    refetchInterval: 3000,
  })

  // Sync panel state from status polling
  if (statusData && panelState === "starting" && statusData.status === "running") {
    setPanelState("running")
  }
  if (statusData && panelState === "running" && statusData.status === "stopped") {
    setPanelState("idle")
  }

  // Poll extension connection status
  const { data: linkInfo } = useQuery({
    queryKey: ["dev-browser-link-info"],
    queryFn: () => api.getDevBrowserLinkInfo(),
    enabled: panelState === "running",
    refetchInterval: 3000,
  })

  // Start mutation
  const startMutation = useMutation({
    mutationFn: async () => {
      if (!containerId) throw new Error("No container")
      return api.startDevBrowser(containerId)
    },
    onSuccess: () => {
      setPanelState("running")
      queryClient.invalidateQueries({ queryKey: ["dev-browser-status"] })
    },
    onError: () => {
      setPanelState("error")
    },
  })

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: async () => {
      if (!containerId) throw new Error("No container")
      return api.stopDevBrowser(containerId)
    },
    onSuccess: () => {
      setPanelState("idle")
      queryClient.invalidateQueries({ queryKey: ["dev-browser-status"] })
    },
  })

  const handleEnable = useCallback(() => setPanelState("confirm"), [])

  const handleConfirm = useCallback(() => {
    setPanelState("starting")
    startMutation.mutate()
  }, [startMutation])

  const handleCancel = useCallback(() => setPanelState("idle"), [])

  const handleStop = useCallback(() => {
    stopMutation.mutate()
  }, [stopMutation])

  const isLoading = sandboxLoading || (!sandboxData?.available && containersLoading)

  // Extension download banner — shown at top of all non-loading states
  const downloadBanner = !bannerDismissed && (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-[hsl(var(--primary))]/5 border-b border-[hsl(var(--primary))]/20 shrink-0">
      <Download className="h-3.5 w-3.5 text-[hsl(var(--primary))] shrink-0" />
      <span className="text-xs font-mono text-[hsl(var(--muted-foreground))] flex-1">
        Install the Chrome Extension to enable browser automation — connects automatically
      </span>
      <a
        href="/downloads/openbox-dev-browser.zip"
        download="openbox-dev-browser.zip"
        className="inline-flex items-center gap-1.5 px-3 py-1 text-[10px] font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer glow-cyan shrink-0"
      >
        <Download className="h-3 w-3" />
        Download Extension
      </a>
      <button
        onClick={() => setBannerDismissed(true)}
        className="p-1 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer shrink-0"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!containerId) {
    return (
      <div className="h-full flex flex-col">
        {downloadBanner}
        <div className="flex-1 flex items-center justify-center grid-pattern">
          <div className="text-center space-y-3">
            <div className="h-16 w-16 rounded-sm bg-[hsl(var(--destructive))]/10 flex items-center justify-center mx-auto glow-coral">
              <AlertCircle className="h-8 w-8 text-[hsl(var(--destructive))]/40" />
            </div>
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No running sandbox found</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1 font-mono">Start a session to create a sandbox</p>
          </div>
        </div>
      </div>
    )
  }

  const extensionConnected = statusData?.extensionConnected ?? false

  // Confirmation dialog
  if (panelState === "confirm") {
    return (
      <div className="h-full flex flex-col">
        {downloadBanner}
        <div className="flex-1 flex items-center justify-center grid-pattern">
        <div className="max-w-md w-full mx-4 p-6 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-sm space-y-5">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
              <MonitorSmartphone className="h-5 w-5 text-[hsl(var(--primary))]" />
            </div>
            <div>
              <h2 className="text-sm font-mono uppercase tracking-wider font-semibold">Enable Dev Browser</h2>
              <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono">Browser automation via Chrome Extension</p>
            </div>
          </div>

          <div className="space-y-3 text-xs text-[hsl(var(--muted-foreground))] font-mono">
            <p>This will start a browser relay server in the sandbox container. You will need:</p>
            <ul className="list-disc list-inside space-y-1.5 ml-1">
              <li>The OpenAgent Browser Chrome Extension installed</li>
              <li>Toggle the extension to Active — it connects automatically</li>
              <li>The agent will be able to control your browser tabs</li>
            </ul>
            <div className="p-3 bg-[hsl(var(--destructive))]/5 border border-[hsl(var(--destructive))]/20 rounded-sm">
              <p className="text-[hsl(var(--destructive))]">
                The agent will have access to interact with browser tabs controlled by the extension. Only enable this if you trust the current session.
              </p>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleCancel}
              className="flex-1 px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 transition-all cursor-pointer"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              className="flex-1 px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer glow-cyan"
            >
              Enable
            </button>
          </div>
        </div>
      </div>
      </div>
    )
  }

  // Starting state
  if (panelState === "starting") {
    return (
      <div className="h-full flex flex-col">
        {downloadBanner}
        <div className="flex-1 flex items-center justify-center grid-pattern">
          <div className="text-center space-y-4">
            <Spinner size="lg" />
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
              Starting relay server...
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Error state
  if (panelState === "error") {
    return (
      <div className="h-full flex flex-col">
        {downloadBanner}
        <div className="flex-1 flex items-center justify-center grid-pattern">
          <div className="text-center space-y-4">
            <div className="h-16 w-16 rounded-sm bg-[hsl(var(--destructive))]/10 flex items-center justify-center mx-auto glow-coral">
              <AlertCircle className="h-8 w-8 text-[hsl(var(--destructive))]/40" />
            </div>
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--destructive))]">
              Failed to start relay server
            </p>
            <button
              onClick={handleCancel}
              className="px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 transition-all cursor-pointer"
            >
              Back
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Running state
  if (panelState === "running") {
    return (
      <div className="h-full flex flex-col">
        {downloadBanner}
        {/* Header */}
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 border-b border-[hsl(var(--border))]/50 bg-[hsl(var(--card))] shrink-0">
          <div className="h-6 w-6 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
            <MonitorSmartphone className="h-3.5 w-3.5 text-[hsl(var(--primary))]" />
          </div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Dev Browser</span>

          {/* Status indicators */}
          <div className="flex items-center gap-3 ml-auto">
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--success))] animate-pulse" />
              <span className="text-[10px] font-mono text-[hsl(var(--success))]">Relay Running</span>
            </div>
            <div className="flex items-center gap-1.5">
              {extensionConnected ? (
                <>
                  <Wifi className="h-3 w-3 text-[hsl(var(--success))]" />
                  <span className="text-[10px] font-mono text-[hsl(var(--success))]">Extension Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3 text-[hsl(var(--muted-foreground))]/60" />
                  <span className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]/60">Waiting for Extension</span>
                </>
              )}
            </div>
            <button
              onClick={handleStop}
              disabled={stopMutation.isPending}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 transition-all cursor-pointer"
            >
              <PowerOff className="h-3 w-3" />
              Stop
            </button>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 flex items-center justify-center grid-pattern">
          <div className="max-w-md w-full mx-4 space-y-4">
            {extensionConnected ? (
              <div className="p-5 bg-[hsl(var(--card))] border border-[hsl(var(--success))]/30 rounded-sm space-y-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-sm bg-[hsl(var(--success))]/10 flex items-center justify-center">
                    <Wifi className="h-5 w-5 text-[hsl(var(--success))]" />
                  </div>
                  <div>
                    <p className="text-sm font-mono font-semibold text-[hsl(var(--success))]">Extension Connected</p>
                    {linkInfo?.client_id && (
                      <p className="text-[10px] font-mono text-[hsl(var(--muted-foreground))] mt-0.5">
                        <Monitor className="h-3 w-3 inline mr-1" />
                        Client {linkInfo.client_id}
                      </p>
                    )}
                  </div>
                </div>
                <p className="text-xs font-mono text-[hsl(var(--muted-foreground))]">
                  Agent can control your browser. Start a conversation and ask the agent to use the browser.
                </p>
              </div>
            ) : (
              <div className="p-5 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-sm space-y-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-sm bg-[hsl(var(--muted))]/30 flex items-center justify-center">
                    <WifiOff className="h-5 w-5 text-[hsl(var(--muted-foreground))]/50" />
                  </div>
                  <div>
                    <p className="text-sm font-mono font-semibold text-[hsl(var(--muted-foreground))]">Waiting for Extension</p>
                    <p className="text-[10px] font-mono text-[hsl(var(--muted-foreground))]/60 mt-0.5">
                      Relay is running, waiting for extension to connect
                    </p>
                  </div>
                </div>
                <div className="p-3 bg-[hsl(var(--surface-1))] rounded-sm">
                  <ol className="list-decimal list-inside space-y-1.5 text-[11px] text-[hsl(var(--muted-foreground))] font-mono">
                    <li>Install the Chrome Extension</li>
                    <li>Login to this site in the same browser</li>
                    <li>Open the extension and toggle <strong className="text-[hsl(var(--foreground))]">Active</strong></li>
                  </ol>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Idle state (default)
  return (
    <div className="h-full flex flex-col">
      {downloadBanner}
      <div className="flex-1 flex items-center justify-center grid-pattern">
        <div className="text-center space-y-4">
          <div className="h-16 w-16 rounded-sm bg-[hsl(var(--primary))]/10 flex items-center justify-center mx-auto glow-cyan">
            <MonitorSmartphone className="h-8 w-8 text-[hsl(var(--primary))]/30" />
          </div>
          <div>
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
              Browser Automation
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]/60 font-mono mt-1">
              Control your Chrome browser through the sandbox agent
            </p>
          </div>
          <button
            onClick={handleEnable}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer glow-cyan"
          >
            <Power className="h-3.5 w-3.5" />
            Enable Dev Browser
          </button>
        </div>
      </div>
    </div>
  )
}
