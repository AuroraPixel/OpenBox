import { useState, useRef, useEffect, useCallback } from "react"
import { Plus, X, Loader2, Check, Circle, AlertCircle, ChevronDown, ChevronUp } from "lucide-react"
import { api } from "@/services/api"
import { wsClient } from "@/services/ws"

interface CreateContainerDialogProps {
  open: boolean
  onClose: () => void
  onCreate: (name: string) => Promise<void>
}

type StepId = "check" | "build" | "create" | "ready"
type StepStatus = "pending" | "active" | "done" | "error"

interface Step {
  id: StepId
  label: string
  status: StepStatus
  message?: string
}

const INITIAL_STEPS: Step[] = [
  { id: "check", label: "Check sandbox image", status: "pending" },
  { id: "build", label: "Build sandbox image", status: "pending" },
  { id: "create", label: "Create container", status: "pending" },
  { id: "ready", label: "Waiting for sandbox ready", status: "pending" },
]

function StepIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case "done":
      return <div className="h-6 w-6 rounded-sm bg-[hsl(var(--success))]/15 flex items-center justify-center glow-green"><Check className="h-3.5 w-3.5 text-[hsl(var(--success))]" /></div>
    case "active":
      return <div className="h-6 w-6 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan"><Loader2 className="h-3.5 w-3.5 text-[hsl(var(--primary))] animate-spin" /></div>
    case "error":
      return <div className="h-6 w-6 rounded-sm bg-[hsl(var(--destructive))]/15 flex items-center justify-center glow-coral"><AlertCircle className="h-3.5 w-3.5 text-[hsl(var(--destructive))]" /></div>
    default:
      return <div className="h-6 w-6 rounded-sm bg-[hsl(var(--muted))]/50 flex items-center justify-center"><Circle className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]/40" /></div>
  }
}

export function CreateContainerDialog({ open, onClose, onCreate }: CreateContainerDialogProps) {
  const [name, setName] = useState("")
  const [phase, setPhase] = useState<"input" | "steps">("input")
  const [steps, setSteps] = useState<Step[]>(INITIAL_STEPS)
  const [buildLogs, setBuildLogs] = useState<string[]>([])
  const [showLogs, setShowLogs] = useState(false)
  const [error, setError] = useState("")
  const logRef = useRef<HTMLDivElement>(null)
  const unsubscribersRef = useRef<Array<() => void>>([])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [buildLogs])

  useEffect(() => {
    if (!open) {
      setPhase("input")
      setSteps(INITIAL_STEPS)
      setBuildLogs([])
      setShowLogs(false)
      setError("")
      setName("")
      // Cleanup any active WS subscriptions
      unsubscribersRef.current.forEach((unsub) => unsub())
      unsubscribersRef.current = []
    }
  }, [open])

  const updateStep = useCallback((id: StepId, update: Partial<Step>) => {
    setSteps(prev => prev.map(s => s.id === id ? { ...s, ...update } : s))
  }, [])

  const runBuild = useCallback((): Promise<void> => {
    return new Promise((resolve, reject) => {
      // Cleanup previous subscriptions
      unsubscribersRef.current.forEach((unsub) => unsub())
      unsubscribersRef.current = []

      let settled = false

      const unsubProgress = wsClient.on("build.progress", (data: unknown) => {
        const d = data as { message?: string }
        if (d.message) {
          setBuildLogs(prev => [...prev, d.message!])
        }
      })

      const unsubComplete = wsClient.on("build.complete", (data: unknown) => {
        if (settled) return
        settled = true
        const d = data as { message?: string }
        setBuildLogs(prev => [...prev, `Done: ${d.message || "Build complete"}`])
        cleanup()
        resolve()
      })

      const unsubError = wsClient.on("build.error", (data: unknown) => {
        if (settled) return
        settled = true
        const d = data as { message?: string }
        setBuildLogs(prev => [...prev, `Error: ${d.message || "Build failed"}`])
        cleanup()
        reject(new Error(d.message || "Build failed"))
      })

      function cleanup() {
        unsubProgress()
        unsubComplete()
        unsubError()
        unsubscribersRef.current = []
      }

      unsubscribersRef.current = [unsubProgress, unsubComplete, unsubError]

      // Trigger the build via WS
      wsClient.startBuild()
    })
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    const trimmedName = name.trim()
    setPhase("steps")
    setError("")
    setBuildLogs([])

    try {
      // Step 1: Check image
      updateStep("check", { status: "active" })
      const { exists } = await api.checkSandboxImage()
      updateStep("check", { status: "done", message: exists ? "Image found" : "Image not found" })

      // Step 2: Build if needed
      if (!exists) {
        updateStep("build", { status: "active", message: "Building..." })
        setShowLogs(true)
        await runBuild()
        updateStep("build", { status: "done", message: "Built successfully" })
      } else {
        updateStep("build", { status: "done", message: "Skipped (image exists)" })
      }

      // Step 3: Create container
      updateStep("create", { status: "active" })
      await onCreate(trimmedName)
      updateStep("create", { status: "done" })

      // Step 4: Ready
      updateStep("ready", { status: "done", message: "Sandbox is running" })

      setTimeout(() => {
        setName("")
        onClose()
      }, 800)
    } catch (err: any) {
      const msg = err.message || "An unexpected error occurred"
      setError(msg)
      setSteps(prev => prev.map(s => s.status === "active" ? { ...s, status: "error", message: msg } : s))
    }
  }

  if (!open) return null

  const isRunning = steps.some(s => s.status === "active")

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center animate-fade-in">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={isRunning ? undefined : onClose} />
      <div className="relative bg-[hsl(var(--card))] rounded-sm border border-[hsl(var(--border))] p-6 w-[480px] shadow-2xl max-h-[80vh] flex flex-col animate-slide-up">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/15 flex items-center justify-center glow-cyan">
              <Plus className="h-4.5 w-4.5 text-[hsl(var(--primary))]" />
            </div>
            <h2 className="text-lg font-display uppercase tracking-wider">Create Sandbox</h2>
          </div>
          {!isRunning && (
            <button onClick={onClose} className="p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer" aria-label="Close dialog">
              <X className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
            </button>
          )}
        </div>

        {phase === "input" ? (
          <form onSubmit={handleSubmit}>
            <div className="mb-5">
              <label className="block text-[10px] font-mono uppercase tracking-wider mb-2">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-sandbox"
                pattern="^[a-zA-Z0-9_-]+$"
                className="w-full px-3.5 py-2.5 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/30 transition-all"
                autoFocus
              />
              <p className="text-[11px] text-[hsl(var(--muted-foreground))] mt-1.5 font-mono">
                Only letters, numbers, hyphens and underscores
              </p>
            </div>
            {error && (
              <div className="mb-4 text-sm text-[hsl(var(--destructive))] bg-[hsl(var(--destructive))]/10 p-3 rounded-sm border border-[hsl(var(--destructive))]/20 font-mono glow-coral">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2.5">
              <button type="button" onClick={onClose} className="px-4 py-2.5 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--border))] transition-all cursor-pointer">
                Cancel
              </button>
              <button type="submit" disabled={!name.trim()} className="px-4 py-2.5 text-sm font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2 cursor-pointer glow-cyan">
                <Plus className="h-4 w-4" />
                Create
              </button>
            </div>
          </form>
        ) : (
          <div className="flex flex-col min-h-0">
            {/* Steps */}
            <div className="space-y-3 mb-4">
              {steps.map((step) => (
                <div key={step.id} className="flex items-start gap-3">
                  <div className="shrink-0">
                    <StepIcon status={step.status} />
                  </div>
                  <div className="flex-1 min-w-0 pt-0.5">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-mono uppercase tracking-wider ${step.status === "pending" ? "text-[hsl(var(--muted-foreground))]/50" : ""}`}>
                        {step.label}
                      </span>
                    </div>
                    {step.message && (
                      <p className={`text-xs font-mono mt-0.5 ${step.status === "error" ? "text-[hsl(var(--destructive))]" : "text-[hsl(var(--muted-foreground))]"}`}>
                        {step.message}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Build logs toggle */}
            {buildLogs.length > 0 && (
              <div className="border-t border-[hsl(var(--border))]/50 pt-3 flex flex-col min-h-0">
                <button
                  onClick={() => setShowLogs(!showLogs)}
                  className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors mb-2 cursor-pointer"
                >
                  {showLogs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  Build logs ({buildLogs.length} lines)
                </button>
                {showLogs && (
                  <div
                    ref={logRef}
                    className="bg-[hsl(var(--background))] rounded-sm border border-[hsl(var(--border))]/50 p-3.5 overflow-y-auto max-h-[200px] font-mono text-[11px] leading-relaxed text-[hsl(var(--muted-foreground))]"
                  >
                    {buildLogs.map((line, i) => (
                      <div key={i} className="whitespace-pre-wrap break-all">{line}</div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="mt-3 text-sm text-[hsl(var(--destructive))] bg-[hsl(var(--destructive))]/10 p-3.5 rounded-sm border border-[hsl(var(--destructive))]/20 font-mono glow-coral">
                {error}
              </div>
            )}

            {/* Footer */}
            <div className="flex justify-end gap-2.5 mt-4">
              {!isRunning && error && (
                <button
                  onClick={() => {
                    setPhase("input")
                    setSteps(INITIAL_STEPS)
                    setBuildLogs([])
                    setShowLogs(false)
                    setError("")
                  }}
                  className="px-4 py-2.5 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--border))] transition-all cursor-pointer"
                >
                  Retry
                </button>
              )}
              {!isRunning && (
                <button onClick={onClose} className="px-4 py-2.5 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] hover:border-[hsl(var(--border))] transition-all cursor-pointer">
                  Close
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
