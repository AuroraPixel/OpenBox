import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { MessageSquare, Terminal, FolderOpen, GitCompare, Globe, MonitorSmartphone } from "lucide-react"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

export type SessionTab = "chat" | "terminal" | "files" | "diff" | "preview" | "browser"

interface SessionTabBarProps {
  sessionId: string
  activeTab: SessionTab
  onTabChange: (tab: SessionTab) => void
}

const tabs: { id: SessionTab; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "terminal", label: "Terminal", icon: Terminal },
  { id: "files", label: "Files", icon: FolderOpen },
  { id: "diff", label: "Diff", icon: GitCompare },
  { id: "preview", label: "Preview", icon: Globe },
  { id: "browser", label: "Browser", icon: MonitorSmartphone },
]

export function SessionTabBar({ sessionId, activeTab, onTabChange }: SessionTabBarProps) {
  // Get container ID for this session
  const { data: sandboxData } = useQuery({
    queryKey: ["session-sandbox", sessionId],
    queryFn: () => api.getSessionSandbox(sessionId),
    refetchInterval: 10000,
  })

  const { data: containerData } = useQuery({
    queryKey: ["containers"],
    queryFn: api.listContainers,
    refetchInterval: 10000,
    enabled: !sandboxData?.available,
  })

  const containerId = useMemo(() => {
    if (sandboxData?.available && sandboxData.container_id) return sandboxData.container_id
    return containerData?.containers?.find((c) => c.status === "running")?.id || null
  }, [sandboxData, containerData])

  // Poll dev-browser extension connection status
  const { data: browserStatus } = useQuery({
    queryKey: ["dev-browser-status", containerId],
    queryFn: () => containerId ? api.getDevBrowserStatus(containerId) : Promise.resolve(null),
    enabled: !!containerId,
    refetchInterval: 5000,
  })

  const extensionConnected = browserStatus?.extensionConnected === true
  const relayRunning = browserStatus?.status === "running"

  return (
    <div className="flex items-center gap-0.5 sm:gap-1 px-2 sm:px-3 h-10 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] shrink-0 overflow-x-auto">
      {tabs.map((tab) => {
        const Icon = tab.icon
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "relative flex items-center gap-1 sm:gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider transition-all cursor-pointer whitespace-nowrap shrink-0",
              activeTab === tab.id
                ? "bg-[hsl(var(--primary))]/10 text-[hsl(var(--primary))] shadow-[0_0_8px_hsl(var(--primary)/0.15)] border border-[hsl(var(--primary))]/20"
                : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]/60"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{tab.label}</span>
            {/* Browser tab status dot */}
            {tab.id === "browser" && relayRunning && (
              <span
                className={cn(
                  "w-1.5 h-1.5 rounded-full shrink-0",
                  extensionConnected
                    ? "bg-[hsl(var(--success))] shadow-[0_0_4px_hsl(var(--success)/0.6)]"
                    : "bg-[hsl(var(--accent))] animate-pulse",
                )}
                title={extensionConnected ? "Extension connected" : "Waiting for extension"}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
