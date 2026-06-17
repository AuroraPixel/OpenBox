import { useState } from "react"
import { Globe, Loader2, Terminal } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface AddMcpServerDialogProps {
  open: boolean
  onClose: () => void
  onAdded: () => void
}

export function AddMcpServerDialog({ open, onClose, onAdded }: AddMcpServerDialogProps) {
  const [name, setName] = useState("")
  const [type, setType] = useState<"stdio" | "remote">("stdio")
  const [command, setCommand] = useState("")
  const [args, setArgs] = useState("")
  const [env, setEnv] = useState("")
  const [url, setUrl] = useState("")
  const [headers, setHeaders] = useState("")
  const [autoConnect, setAutoConnect] = useState(true)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")

  const reset = () => {
    setName("")
    setType("stdio")
    setCommand("")
    setArgs("")
    setEnv("")
    setUrl("")
    setHeaders("")
    setAutoConnect(true)
    setError("")
    setAdding(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleAdd = async () => {
    setError("")
    if (!name.trim()) {
      setError("Name is required")
      return
    }
    setAdding(true)
    try {
      const data: Record<string, unknown> = { name: name.trim(), type }
      if (type === "stdio") {
        if (!command.trim()) {
          setError("Command is required for stdio servers")
          setAdding(false)
          return
        }
        data.command = command.trim()
        data.args = args.trim() ? args.trim().split(/\s+/) : []
        // Parse env as KEY=VALUE lines
        if (env.trim()) {
          const envObj: Record<string, string> = {}
          for (const line of env.trim().split("\n")) {
            const eqIdx = line.indexOf("=")
            if (eqIdx > 0) {
              envObj[line.slice(0, eqIdx).trim()] = line.slice(eqIdx + 1).trim()
            }
          }
          data.env = envObj
        }
      } else {
        if (!url.trim()) {
          setError("URL is required for remote servers")
          setAdding(false)
          return
        }
        data.url = url.trim()
        // Parse headers as KEY: VALUE lines
        if (headers.trim()) {
          const hdrs: Record<string, string> = {}
          for (const line of headers.trim().split("\n")) {
            const colonIdx = line.indexOf(":")
            if (colonIdx > 0) {
              hdrs[line.slice(0, colonIdx).trim()] = line.slice(colonIdx + 1).trim()
            }
          }
          data.headers = hdrs
        }
      }

      await api.addMcpServer(data as Parameters<typeof api.addMcpServer>[0])

      if (autoConnect) {
        try {
          await api.connectMcp(name.trim())
        } catch {
          // Server added but connection failed — still OK
        }
      }

      onAdded()
      handleClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add server")
    } finally {
      setAdding(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Add MCP Server">
      <div className="p-6 space-y-5 animate-slide-up">
        {/* Name */}
        <div>
          <label htmlFor="mcp-name" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
            Server Name
          </label>
          <input
            id="mcp-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="filesystem"
            className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
          />
        </div>

        {/* Type selector */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-2">
            Server Type
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setType("stdio")}
              className={cn(
                "flex items-center gap-2.5 p-3 rounded-sm border text-left transition-all cursor-pointer",
                type === "stdio"
                  ? "border-[hsl(var(--primary))]/50 bg-[hsl(var(--primary))]/5 ring-1 ring-[hsl(var(--primary))]/20 glow-cyan"
                  : "border-[hsl(var(--border))] hover:border-[hsl(var(--muted-foreground))]/30",
              )}
            >
              <Terminal className={cn("h-4 w-4", type === "stdio" ? "text-[hsl(var(--primary))]" : "text-[hsl(var(--muted-foreground))]")} />
              <div>
                <div className="text-sm font-mono uppercase tracking-wider">stdio</div>
                <div className="text-[11px] text-[hsl(var(--muted-foreground))]">Local process</div>
              </div>
            </button>
            <button
              onClick={() => setType("remote")}
              className={cn(
                "flex items-center gap-2.5 p-3 rounded-sm border text-left transition-all cursor-pointer",
                type === "remote"
                  ? "border-[hsl(var(--primary))]/50 bg-[hsl(var(--primary))]/5 ring-1 ring-[hsl(var(--primary))]/20 glow-cyan"
                  : "border-[hsl(var(--border))] hover:border-[hsl(var(--muted-foreground))]/30",
              )}
            >
              <Globe className={cn("h-4 w-4", type === "remote" ? "text-[hsl(var(--primary))]" : "text-[hsl(var(--muted-foreground))]")} />
              <div>
                <div className="text-sm font-mono uppercase tracking-wider">remote</div>
                <div className="text-[11px] text-[hsl(var(--muted-foreground))]">HTTP endpoint</div>
              </div>
            </button>
          </div>
        </div>

        {/* stdio fields */}
        {type === "stdio" && (
          <div className="space-y-4">
            <div>
              <label htmlFor="mcp-command" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Command
              </label>
              <input
                id="mcp-command"
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="npx"
                className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all font-mono"
              />
            </div>
            <div>
              <label htmlFor="mcp-args" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Arguments <span className="opacity-60">(space-separated)</span>
              </label>
              <input
                id="mcp-args"
                type="text"
                value={args}
                onChange={(e) => setArgs(e.target.value)}
                placeholder="-y @modelcontextprotocol/server-filesystem /workspace"
                className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all font-mono"
              />
            </div>
            <div>
              <label htmlFor="mcp-env" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Environment Variables <span className="opacity-60">(KEY=VALUE, one per line)</span>
              </label>
              <textarea
                id="mcp-env"
                value={env}
                onChange={(e) => setEnv(e.target.value)}
                placeholder="NODE_ENV=production"
                rows={3}
                className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all font-mono resize-y"
              />
            </div>
          </div>
        )}

        {/* remote fields */}
        {type === "remote" && (
          <div className="space-y-4">
            <div>
              <label htmlFor="mcp-url" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Server URL
              </label>
              <input
                id="mcp-url"
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://api.example.com/mcp"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
              />
            </div>
            <div>
              <label htmlFor="mcp-headers" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Headers <span className="opacity-60">(KEY: VALUE, one per line)</span>
              </label>
              <textarea
                id="mcp-headers"
                value={headers}
                onChange={(e) => setHeaders(e.target.value)}
                placeholder="X-Api-Key: your-api-key"
                rows={2}
                className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all font-mono resize-y"
              />
            </div>
          </div>
        )}

        {/* Auto-connect */}
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <div className="relative">
            <input
              type="checkbox"
              checked={autoConnect}
              onChange={(e) => setAutoConnect(e.target.checked)}
              className="peer sr-only"
            />
            <div className={cn(
              "h-5 w-9 rounded-sm transition-colors",
              autoConnect ? "bg-[hsl(var(--primary))] glow-cyan" : "bg-[hsl(var(--muted))]",
            )} />
            <div className={cn(
              "absolute top-0.5 left-0.5 h-4 w-4 rounded-sm bg-white shadow transition-transform",
              autoConnect && "translate-x-4",
            )} />
          </div>
          <span className="text-sm font-mono text-[hsl(var(--muted-foreground))] group-hover:text-[hsl(var(--foreground))] transition-colors">
            Auto-connect after adding
          </span>
        </label>

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] font-mono glow-coral">
            <div className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--destructive))] shrink-0" />
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleAdd}
            disabled={adding}
            className={cn(
              "px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
              "hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed",
              "flex items-center gap-2 glow-cyan",
            )}
          >
            {adding && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Add Server
          </button>
        </div>
      </div>
    </Modal>
  )
}
