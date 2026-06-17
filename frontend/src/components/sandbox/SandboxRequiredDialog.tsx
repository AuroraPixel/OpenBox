import { useState, useCallback, useRef, useEffect } from "react"
import { Loader2, Check, AlertTriangle, RotateCcw } from "lucide-react"
import { useUIStore } from "@/stores/ui"
import { api } from "@/services/api"
import { wsClient } from "@/services/ws"
import { cn } from "@/lib/utils"

type Phase = "creating" | "done" | "error"

export function SandboxRequiredDialog() {
  const open = useUIStore((s) => s.sandboxDialogOpen)
  const callback = useUIStore((s) => s.sandboxDialogCallback)
  const closeSandboxDialog = useUIStore((s) => s.closeSandboxDialog)
  const setSandboxAvailable = useUIStore((s) => s.setSandboxAvailable)

  const [phase, setPhase] = useState<Phase>("creating")
  const [statusMessage, setStatusMessage] = useState("")
  const [error, setError] = useState("")
  const unsubscribersRef = useRef<Array<() => void>>([])
  const startedRef = useRef(false)

  // Cleanup WS subscriptions when dialog closes
  useEffect(() => {
    if (!open) {
      unsubscribersRef.current.forEach((unsub) => unsub())
      unsubscribersRef.current = []
      startedRef.current = false
    }
  }, [open])

  const handleDone = useCallback(() => {
    setSandboxAvailable(true)
    setPhase("done")
    setStatusMessage("Sandbox is ready!")
    setTimeout(() => {
      closeSandboxDialog()
      callback?.()
      // Reset for next use
      setTimeout(() => {
        setPhase("creating")
        setStatusMessage("")
        setError("")
      }, 200)
    }, 600)
  }, [setSandboxAvailable, closeSandboxDialog, callback])

  const doCreate = useCallback(async () => {
    setPhase("creating")
    setError("")
    setStatusMessage("Checking sandbox...")

    try {
      // First check if sandbox already available
      try {
        const status = await api.getSandboxStatus()
        if (status.available) {
          handleDone()
          return
        }

        // Check for stopped containers — auto-start the first one
        const stopped = (status.containers || []).filter((c: { status: string }) => c.status === "stopped")
        if (stopped.length > 0) {
          setStatusMessage("Starting container...")
          await api.startContainer(stopped[0].id)
          handleDone()
          return
        }
      } catch {
        // Health check failed — proceed to create
      }

      // Check sandbox image
      setStatusMessage("Checking sandbox image...")
      const { exists } = await api.checkSandboxImage()

      if (!exists) {
        setStatusMessage("Building sandbox image...")
        await new Promise<void>((resolve, reject) => {
          unsubscribersRef.current.forEach((unsub) => unsub())
          unsubscribersRef.current = []

          let settled = false

          const unsubProgress = wsClient.on("build.progress", (data: unknown) => {
            const d = data as { message?: string }
            if (d.message) setStatusMessage(d.message)
          })

          const unsubComplete = wsClient.on("build.complete", () => {
            if (settled) return
            settled = true
            cleanup()
            resolve()
          })

          const unsubError = wsClient.on("build.error", (data: unknown) => {
            if (settled) return
            settled = true
            const d = data as { message?: string }
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
          wsClient.startBuild()
        })
      }

      setStatusMessage("Creating container...")
      const containerName = `sandbox-${Date.now().toString(36)}`
      await api.createContainer({ name: containerName })

      handleDone()
    } catch (err: any) {
      setPhase("error")
      setError(err.message || "Failed to create sandbox")
    }
  }, [handleDone])

  // Auto-start creation as soon as dialog opens — no user confirmation needed
  useEffect(() => {
    if (open && !startedRef.current) {
      startedRef.current = true
      doCreate()
    }
  }, [open, doCreate])

  const handleRetry = useCallback(() => {
    startedRef.current = false
    setPhase("creating")
    setError("")
    // Trigger re-create on next tick
    setTimeout(() => {
      startedRef.current = true
      doCreate()
    }, 0)
  }, [doCreate])

  const handleDismiss = useCallback(() => {
    closeSandboxDialog()
    setTimeout(() => {
      setPhase("creating")
      setStatusMessage("")
      setError("")
    }, 200)
  }, [closeSandboxDialog])

  if (!open) return null

  return (
    <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-slide-up">
      <div className={cn(
        "flex items-center gap-3 px-5 py-3.5 rounded-sm border shadow-lg backdrop-blur-sm",
        "bg-[hsl(var(--card))]/95 min-w-[320px] max-w-[480px]",
        phase === "error"
          ? "border-[hsl(var(--destructive))]/30 shadow-[0_0_20px_hsl(var(--destructive)/0.15)]"
          : phase === "done"
            ? "border-[hsl(var(--success))]/30 shadow-[0_0_20px_hsl(var(--success)/0.15)]"
            : "border-[hsl(var(--primary))]/20 shadow-[0_0_20px_hsl(var(--primary)/0.1)]",
      )}>
        {phase === "creating" && (
          <>
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/10 flex items-center justify-center shrink-0">
              <Loader2 className="h-4.5 w-4.5 text-[hsl(var(--primary))] animate-spin" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-display uppercase tracking-wider text-[hsl(var(--primary))]">Creating Sandbox</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono truncate mt-0.5">{statusMessage || "Initializing..."}</p>
            </div>
          </>
        )}

        {phase === "done" && (
          <>
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--success))]/10 flex items-center justify-center shrink-0">
              <Check className="h-4.5 w-4.5 text-[hsl(var(--success))]" />
            </div>
            <p className="text-xs font-display uppercase tracking-wider text-[hsl(var(--success))]">Sandbox Ready</p>
          </>
        )}

        {phase === "error" && (
          <>
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--destructive))]/10 flex items-center justify-center shrink-0">
              <AlertTriangle className="h-4.5 w-4.5 text-[hsl(var(--destructive))]" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-display uppercase tracking-wider text-[hsl(var(--destructive))]">Sandbox Failed</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono truncate mt-0.5">{error}</p>
            </div>
            <button
              onClick={handleRetry}
              className="p-1.5 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] shrink-0"
              aria-label="Retry"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleDismiss}
              className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] transition-colors cursor-pointer shrink-0 px-1"
            >
              Dismiss
            </button>
          </>
        )}
      </div>
    </div>
  )
}
