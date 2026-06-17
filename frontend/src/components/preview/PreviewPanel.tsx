import { useState, useMemo, useEffect, useRef, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import { Globe, RefreshCw, ExternalLink, AlertCircle, Radio } from "lucide-react"
import { api } from "@/services/api"
import { Spinner } from "@/components/ui/Spinner"
import { cn } from "@/lib/utils"

interface DetectedPort {
  port: number
  pid: number | null
  process: string
  command: string
}

interface PreviewPanelProps {
  sessionId: string
}

export function PreviewPanel({ sessionId }: PreviewPanelProps) {
  const [port, setPort] = useState("")
  const [activePort, setActivePort] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [detectedPorts, setDetectedPorts] = useState<DetectedPort[]>([])
  const prevPortsRef = useRef<string>("")

  // 1. Get the session's bound container (not just first running)
  const { data: sandboxData, isLoading: sandboxLoading } = useQuery({
    queryKey: ["session-sandbox", sessionId],
    queryFn: () => api.getSessionSandbox(sessionId),
    refetchInterval: 5000,
  })

  // Fallback: if no session sandbox, use first running container
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
    // Fallback to first running container
    return containerData?.containers?.find((c) => c.status === "running")?.id || null
  }, [sandboxData, containerData])

  // 2. Poll listening ports from the container
  const { data: portsData } = useQuery({
    queryKey: ["listening-ports", containerId],
    queryFn: () => containerId ? api.getListeningPorts(containerId) : Promise.resolve({ ports: [] }),
    enabled: !!containerId,
    refetchInterval: 3000,
  })

  // Detect newly appeared ports and auto-open the first one
  useEffect(() => {
    if (!portsData?.ports) return
    const ports = portsData.ports
    setDetectedPorts(ports)

    const portsKey = ports.map((p) => p.port).sort().join(",")
    if (portsKey !== prevPortsRef.current) {
      const oldPorts = new Set(prevPortsRef.current.split(",").filter(Boolean).map(Number))
      prevPortsRef.current = portsKey

      // Find newly appeared ports
      const newPorts = ports.filter((p) => !oldPorts.has(p.port))
      if (newPorts.length > 0 && !activePort) {
        // Auto-open the first new port
        const newPort = newPorts[0].port.toString()
        setPort(newPort)
        setActivePort(newPort)
        setRefreshKey((k) => k + 1)
      }
    }
  }, [portsData, activePort])

  const previewUrl = useMemo(() => {
    if (!containerId || !activePort) return null
    return `/api/containers/${containerId}/preview/${activePort}/`
  }, [containerId, activePort])

  const handleOpen = useCallback((p?: string) => {
    const target = (p || port).trim()
    if (target && /^\d+$/.test(target)) {
      setPort(target)
      setActivePort(target)
      setRefreshKey((k) => k + 1)
    }
  }, [port])

  const handleRefresh = () => setRefreshKey((k) => k + 1)

  const handleOpenExternal = () => {
    if (previewUrl) window.open(previewUrl, "_blank")
  }

  const isLoading = sandboxLoading || (!sandboxData?.available && containersLoading)

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!containerId) {
    return (
      <div className="h-full flex items-center justify-center grid-pattern">
        <div className="text-center space-y-3">
          <div className="h-16 w-16 rounded-sm bg-[hsl(var(--destructive))]/10 flex items-center justify-center mx-auto glow-coral">
            <AlertCircle className="h-8 w-8 text-[hsl(var(--destructive))]/40" />
          </div>
          <div>
            <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No running sandbox found</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]/60 mt-1 font-mono">Start a session to create a sandbox</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-2.5 px-3.5 py-2.5 border-b border-[hsl(var(--border))]/50 bg-[hsl(var(--card))] shrink-0">
        <div className="h-6 w-6 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
          <Globe className="h-3.5 w-3.5 text-[hsl(var(--primary))]" />
        </div>
        <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">localhost:</span>
        <input
          type="text"
          value={port}
          onChange={(e) => setPort(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleOpen()}
          placeholder="3000"
          className="w-16 px-2.5 py-1.5 text-xs rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/30 transition-all tabular-nums font-mono"
        />
        <button
          onClick={() => handleOpen()}
          className="px-3.5 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer glow-cyan"
        >
          Open
        </button>
        {activePort && (
          <>
            <div className="h-4 w-px bg-[hsl(var(--border))]/50" />
            <button
              onClick={handleRefresh}
              className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer"
              title="Refresh"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleOpenExternal}
              className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer"
              title="Open in new tab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          </>
        )}
        <span className="text-[10px] text-[hsl(var(--muted-foreground))]/60 ml-auto font-mono tabular-nums">
          {containerId.slice(0, 8)}
          {activePort && `:${activePort}`}
        </span>
      </div>

      {/* Detected ports bar */}
      {detectedPorts.length > 0 && (
        <div className="flex items-center gap-2 px-3.5 py-2 border-b border-[hsl(var(--border))]/30 bg-[hsl(var(--card))]/50 shrink-0 overflow-x-auto">
          <div className="flex items-center gap-1.5 shrink-0">
            <Radio className="h-3 w-3 text-[hsl(var(--success))] glow-green" />
            <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">Detected:</span>
          </div>
          {detectedPorts.map((dp) => (
            <button
              key={dp.port}
              onClick={() => handleOpen(dp.port.toString())}
              title={dp.command || dp.process || `Port ${dp.port}`}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[10px] font-mono font-medium transition-all cursor-pointer tabular-nums",
                activePort === dp.port.toString()
                  ? "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] glow-cyan"
                  : "bg-[hsl(var(--muted))]/50 text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))] border border-[hsl(var(--border))]/30",
              )}
            >
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                activePort === dp.port.toString() ? "bg-[hsl(var(--primary-foreground))]" : "bg-[hsl(var(--success))]",
              )} />
              {dp.port}
              {dp.process && (
                <span className="opacity-60 font-mono uppercase">{dp.process}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Preview iframe or empty state */}
      <div className="flex-1 overflow-hidden bg-white">
        {previewUrl ? (
          <iframe
            key={refreshKey}
            src={previewUrl}
            className="w-full h-full border-0"
            title={`Preview port ${activePort}`}
            sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
          />
        ) : (
          <div className="h-full flex items-center justify-center bg-[hsl(var(--background))] grid-pattern">
            <div className="text-center space-y-3">
              <div className="h-16 w-16 rounded-sm bg-[hsl(var(--primary))]/10 flex items-center justify-center mx-auto glow-cyan">
                <Globe className="h-8 w-8 text-[hsl(var(--primary))]/30" />
              </div>
              {detectedPorts.length > 0 ? (
                <>
                  <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
                    Click a detected port above to preview
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">
                    Enter a port number and click Open to preview
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]/60 font-mono">
                    Ports will be auto-detected when services start
                  </p>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
