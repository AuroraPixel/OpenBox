import { useState } from "react"
import { Plus, Terminal, Square, Play, Trash2, Box, Cpu, MemoryStick, HardDrive } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { CreateContainerDialog } from "@/components/containers/CreateContainerDialog"
import { ConfirmDialog } from "@/components/ui/ConfirmDialog"
import { useToast } from "@/components/ui/Toast"
import { Badge } from "@/components/ui/Badge"
import { cn, formatBytes } from "@/lib/utils"
import { api } from "@/services/api"
import type { ContainerInfo } from "@/types"

interface SandboxPageProps {
  containers: ContainerInfo[]
  onTerminal: (id: string) => void
  showCreate: boolean
  onShowCreate: (show: boolean) => void
}

const statusColors: Record<string, { dot: string; variant: "success" | "default" | "warning" | "error" }> = {
  running: { dot: "bg-[hsl(var(--success))] shadow-[0_0_6px_hsl(var(--success))]", variant: "success" },
  stopped: { dot: "bg-[hsl(var(--muted-foreground))]/40", variant: "default" },
  creating: { dot: "bg-[hsl(var(--accent))] shadow-[0_0_6px_hsl(var(--accent))]", variant: "warning" },
  error: { dot: "bg-[hsl(var(--destructive))] shadow-[0_0_6px_hsl(var(--destructive))]", variant: "error" },
}

export function SandboxPage({ containers, onTerminal, showCreate, onShowCreate }: SandboxPageProps) {
  const handleCreate = async (name: string) => {
    await api.createContainer({ name })
  }

  const handleStop = async (id: string) => {
    await api.stopContainer(id)
  }

  const handleStart = async (id: string) => {
    await api.startContainer(id)
  }

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const { addToast } = useToast()

  const handleDelete = async () => {
    if (!deleteTarget) return
    const id = deleteTarget
    setDeleteTarget(null)
    try {
      await api.deleteContainer(id)
      addToast("success", "Sandbox deleted")
    } catch (err) {
      addToast("error", err instanceof Error ? err.message : "Failed to delete sandbox")
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-[hsl(var(--background))] grid-pattern">
      <div className="max-w-4xl mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 flex items-center justify-center shadow-[0_0_12px_hsl(var(--primary)/0.2)]">
              <Box className="h-5 w-5 text-[hsl(var(--primary))] glow-cyan" />
            </div>
            <div>
              <h1 className="text-xl font-display font-bold text-[hsl(var(--foreground))]">Sandbox Management</h1>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge variant="outline"><span className="tabular-nums font-mono">{containers.length}</span> <span className="font-mono uppercase tracking-wider">total</span></Badge>
              </div>
            </div>
          </div>
          <button
            onClick={() => onShowCreate(true)}
            disabled={containers.length > 0}
            className="flex items-center gap-2 px-4 py-2.5 rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-sm font-mono uppercase tracking-wider hover:opacity-90 transition-opacity cursor-pointer shadow-[0_0_14px_hsl(var(--primary)/0.3)] animate-glow-pulse"
          >
            <Plus className="h-4 w-4" />
            {containers.length > 0 ? "One Sandbox Limit" : "New Sandbox"}
          </button>
        </div>

        {containers.length === 0 ? (
          <div className="text-center py-20">
            <div className="h-20 w-20 rounded-sm bg-[hsl(var(--muted))]/30 border border-[hsl(var(--border))]/30 flex items-center justify-center mx-auto mb-5">
              <Box className="h-10 w-10 opacity-30 text-[hsl(var(--muted-foreground))]" />
            </div>
            <h3 className="text-lg font-display font-semibold mb-1.5 text-[hsl(var(--foreground))]">No sandboxes yet</h3>
            <p className="text-sm text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider">Create one to get started</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {containers.map((c) => {
              const st = statusColors[c.status] || statusColors.stopped
              return (
                <div key={c.id} className="rounded-sm border border-[hsl(var(--border))]/50 bg-[hsl(var(--card))] p-4 hover:border-[hsl(var(--primary))]/20 hover:shadow-[0_0_10px_hsl(var(--primary)/0.08)] transition-all">
                  <div className="flex items-center gap-3 mb-3">
                    <div className={cn("h-2.5 w-2.5 rounded-sm", st.dot)} />
                    <h3 className="font-display font-semibold flex-1 text-[hsl(var(--foreground))]">{c.name}</h3>
                    <Badge variant={st.variant}><span className="font-mono uppercase tracking-wider">{c.status}</span></Badge>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-[hsl(var(--muted-foreground))] mb-3">
                    <span className="bg-[hsl(var(--muted))]/30 px-2 py-0.5 rounded-sm font-mono border border-[hsl(var(--border))]/20">Image: {c.image}</span>
                    <span className="font-mono tabular-nums">Created: {new Date(c.created_at).toLocaleDateString()}</span>
                    {c.port && <span className="tabular-nums font-mono">Port: {c.port}</span>}
                  </div>
                  {c.status === "running" && (
                    <ContainerSystemInfo containerId={c.id} />
                  )}
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[hsl(var(--border))]/30">
                    {c.status === "running" && (
                      <>
                        <button onClick={() => onTerminal(c.id)} className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--primary))]/20 text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10 hover:border-[hsl(var(--primary))]/30 transition-all cursor-pointer">
                          <Terminal className="h-3.5 w-3.5" /> Terminal
                        </button>
                        <button onClick={() => handleStop(c.id)} className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--accent))]/20 text-[hsl(var(--accent))] hover:bg-[hsl(var(--accent))]/10 hover:border-[hsl(var(--accent))]/30 transition-all cursor-pointer">
                          <Square className="h-3.5 w-3.5" /> Stop
                        </button>
                      </>
                    )}
                    {c.status === "stopped" && (
                      <button onClick={() => handleStart(c.id)} className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--success))]/20 text-[hsl(var(--success))] hover:bg-[hsl(var(--success))]/10 hover:border-[hsl(var(--success))]/30 transition-all cursor-pointer">
                        <Play className="h-3.5 w-3.5" /> Start
                      </button>
                    )}
                    <button onClick={() => setDeleteTarget(c.id)} className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--destructive))]/20 text-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/10 hover:border-[hsl(var(--destructive))]/30 transition-all cursor-pointer ml-auto">
                      <Trash2 className="h-3.5 w-3.5" /> Delete
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <CreateContainerDialog
        open={showCreate}
        onClose={() => onShowCreate(false)}
        onCreate={handleCreate}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Sandbox"
        message="Are you sure you want to delete this sandbox? All data inside will be lost."
        confirmLabel="Delete"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}

function ContainerSystemInfo({ containerId }: { containerId: string }) {
  const { data: sysInfo } = useQuery({
    queryKey: ["systemInfo", containerId],
    queryFn: () => api.getSystemInfo(containerId),
    refetchInterval: 10000,
  })

  if (!sysInfo) return null

  return (
    <div className="flex items-center gap-4 text-xs text-[hsl(var(--muted-foreground))] mt-2 pt-2.5 border-t border-[hsl(var(--border))]/30">
      <div className="flex items-center gap-1.5 bg-[hsl(var(--muted))]/30 px-2.5 py-1 rounded-sm border border-[hsl(var(--border))]/20">
        <Cpu className="h-3 w-3 text-[hsl(var(--primary))]" />
        <span className="font-mono font-medium tabular-nums">{sysInfo.cpu.percent.toFixed(0)}%</span>
      </div>
      <div className="flex items-center gap-1.5 bg-[hsl(var(--muted))]/30 px-2.5 py-1 rounded-sm border border-[hsl(var(--border))]/20">
        <MemoryStick className="h-3 w-3 text-[hsl(var(--accent))]" />
        <span className="font-mono font-medium tabular-nums">{formatBytes(sysInfo.memory.used)} / {formatBytes(sysInfo.memory.total)}</span>
      </div>
      <div className="flex items-center gap-1.5 bg-[hsl(var(--muted))]/30 px-2.5 py-1 rounded-sm border border-[hsl(var(--border))]/20">
        <HardDrive className="h-3 w-3 text-[hsl(var(--success))]" />
        <span className="font-mono font-medium tabular-nums">{sysInfo.disk.percent.toFixed(0)}%</span>
      </div>
    </div>
  )
}
