import { X, Terminal as TerminalIcon } from "lucide-react"
import { Terminal } from "./Terminal"
import type { ContainerInfo } from "@/types"

interface TerminalTab {
  containerId: string
  containerName: string
}

interface TerminalTabsProps {
  tabs: TerminalTab[]
  activeTab: string | null
  containers: ContainerInfo[]
  onSelectTab: (containerId: string) => void
  onCloseTab: (containerId: string) => void
}

export function TerminalTabs({ tabs, activeTab, containers, onSelectTab, onCloseTab }: TerminalTabsProps) {
  if (tabs.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-[hsl(var(--muted-foreground))] grid-pattern">
        <div className="h-20 w-20 rounded-sm bg-[hsl(var(--muted))]/30 flex items-center justify-center mb-5">
          <TerminalIcon className="h-10 w-10 opacity-30" />
        </div>
        <p className="text-lg font-display uppercase tracking-wider">No Terminal Open</p>
        <p className="text-sm mt-1.5 text-[hsl(var(--muted-foreground))]/60 font-mono">Select a running sandbox and click the terminal icon</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="flex border-b border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]">
        {tabs.map((tab) => {
          const container = containers.find(c => c.id === tab.containerId)
          const isRunning = container?.status === "running"
          return (
            <div
              key={tab.containerId}
              onClick={() => onSelectTab(tab.containerId)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm cursor-pointer border-b-2 transition-all ${
                activeTab === tab.containerId
                  ? "border-[hsl(var(--primary))] text-[hsl(var(--foreground))] bg-[hsl(var(--primary))]/5 glow-cyan"
                  : "border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]/30"
              }`}
            >
              <TerminalIcon className="h-3.5 w-3.5" />
              <span className="max-w-[100px] truncate font-mono font-medium">{tab.containerName}</span>
              {!isRunning && <span className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--accent))] bg-[hsl(var(--accent))]/10 px-1.5 py-0.5 rounded-sm">(stopped)</span>}
              <button
                onClick={(e) => { e.stopPropagation(); onCloseTab(tab.containerId) }}
                className="ml-1 p-0.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
                aria-label="Close tab"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )
        })}
      </div>
      {/* Terminal content */}
      <div className="flex-1 bg-[hsl(var(--terminal-bg))]">
        {tabs.map((tab) => (
          <div key={tab.containerId} className={`h-full ${activeTab === tab.containerId ? "" : "hidden"}`}>
            <Terminal containerId={tab.containerId} />
          </div>
        ))}
      </div>
    </div>
  )
}
