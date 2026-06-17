import { useState, useRef, useEffect, useCallback } from "react"
import { Send, Sparkles, Code, FileSearch, Bug, Rocket, MonitorSmartphone, ExternalLink } from "lucide-react"
import { useSessionStore } from "@/stores/session"
import { useUIStore } from "@/stores/ui"
import { useToast } from "@/components/ui/Toast"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

interface WelcomePageProps {
  onNavigate: (path: string) => void
}

const suggestions = [
  { icon: <Code className="h-4 w-4" />, label: "Build a feature", prompt: "Help me build a new REST API endpoint with validation and tests" },
  { icon: <Bug className="h-4 w-4" />, label: "Fix a bug", prompt: "I have a bug where the login page crashes when the session expires" },
  { icon: <FileSearch className="h-4 w-4" />, label: "Explore codebase", prompt: "Explain the architecture of this project and key design patterns used" },
  { icon: <Rocket className="h-4 w-4" />, label: "Optimize performance", prompt: "Analyze this project for performance bottlenecks and suggest improvements" },
]

export function WelcomePage({ onNavigate }: WelcomePageProps) {
  const { addToast } = useToast()
  const addSession = useSessionStore((s) => s.addSession)
  const switchSession = useSessionStore((s) => s.switchSession)
  const pendingModel = useUIStore((s) => s.pendingModel)
  const pendingAgent = useUIStore((s) => s.pendingAgent)
  const setPendingModel = useUIStore((s) => s.setPendingModel)
  const setPendingAgent = useUIStore((s) => s.setPendingAgent)
  const [text, setText] = useState("")
  const [isCreating, setIsCreating] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = "auto"
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px"
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [text, adjustHeight])

  const doStartChat = useCallback(async (content: string) => {
    setIsCreating(true)
    try {
      const createOpts: { model?: string; agent?: string } = {}
      if (pendingModel) createOpts.model = pendingModel
      if (pendingAgent) createOpts.agent = pendingAgent
      const session = await api.createSession(Object.keys(createOpts).length > 0 ? createOpts : undefined)
      addSession(session)
      switchSession(session.id)
      setPendingModel(null)
      setPendingAgent(null)
      await api.sendMessageAsync(session.id, content)
      onNavigate(`/session/${session.id}`)
    } catch {
      addToast("error", "Failed to create session. Please try again.")
    } finally {
      setIsCreating(false)
    }
  }, [addSession, switchSession, onNavigate, pendingModel, pendingAgent, setPendingModel, setPendingAgent, addToast])

  const handleStartChat = useCallback(async (message?: string) => {
    const content = message || text.trim()
    if (!content || isCreating) return

    // No sandbox pre-check — backend auto-creates via acquire() in the agent loop.
    // This avoids the race condition where WS _ensure_user_container is still creating
    // while the frontend check sees "not available" and pops a dialog.
    doStartChat(content)
  }, [text, isCreating, doStartChat])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleStartChat()
    }
  }, [handleStartChat])

  return (
    <div className="h-full flex flex-col bg-[hsl(var(--background))] grid-pattern">
      {/* Browser Use banner */}
      <a
        href="/#/browser-use-guide"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-3 px-4 py-2.5 bg-[hsl(var(--primary))]/5 border-b border-[hsl(var(--primary))]/15 shrink-0 hover:bg-[hsl(var(--primary))]/10 transition-colors cursor-pointer"
      >
        <MonitorSmartphone className="h-3.5 w-3.5 text-[hsl(var(--primary))] shrink-0" />
        <span className="text-xs font-mono text-[hsl(var(--muted-foreground))] flex-1">
          New: Browser Use — Let the AI agent control your Chrome browser
        </span>
        <span className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--primary))]">
          Learn More <ExternalLink className="h-3 w-3" />
        </span>
      </a>

      <div className="flex-1 flex flex-col items-center justify-center px-3 sm:px-4">
      <div className="w-full max-w-2xl">
        {/* Hero */}
        <div className="text-center mb-6 sm:mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 sm:w-16 sm:h-16 rounded-sm bg-[hsl(var(--primary))]/15 border border-[hsl(var(--primary))]/30 mb-4 sm:mb-5 shadow-[0_0_20px_hsl(var(--primary)/0.3)] glow-cyan">
            <Sparkles className="h-7 w-7 sm:h-8 sm:w-8 text-[hsl(var(--primary))] animate-glow-pulse" />
          </div>
          <h1 className="text-2xl sm:text-3xl font-display font-bold tracking-tight mb-2 sm:mb-2.5 text-[hsl(var(--foreground))]">What can I help you build?</h1>
          <p className="text-[hsl(var(--muted-foreground))] text-sm sm:text-base leading-relaxed font-mono">
            AI coding agent with sandbox execution, file editing, and codebase understanding.
          </p>
          <span className="inline-block mt-3 px-2 py-0.5 rounded-sm bg-[hsl(var(--accent))]/10 border border-[hsl(var(--accent))]/20 text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--accent))] glow-amber">
            Retro-Futurism Mode
          </span>
        </div>

        {/* Central input */}
        <div className="relative mb-4 sm:mb-6">
          <div className={cn(
            "rounded-sm border bg-[hsl(var(--card))] shadow-lg transition-all",
            "border-[hsl(var(--border))] focus-within:border-[hsl(var(--primary))]/20 focus-within:ring-2 focus-within:ring-[hsl(var(--primary))]/10 focus-within:shadow-[0_0_20px_hsl(var(--primary)/0.15)]",
          )}>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe what you want to build, fix, or explore..."
              rows={1}
              className="w-full bg-[hsl(var(--surface-1))] text-sm font-mono resize-none focus:outline-none min-h-[52px] max-h-[160px] px-4 pt-4 pb-12 text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/50 rounded-sm"
            />
            <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
              <div className="hidden sm:flex items-center gap-2 text-[11px] text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-wider">
                <kbd className="px-1.5 py-0.5 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30 text-[10px] font-mono font-medium">Enter</kbd>
                <span>to send</span>
                <span className="mx-1 opacity-30">|</span>
                <kbd className="px-1.5 py-0.5 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30 text-[10px] font-mono font-medium">Shift+Enter</kbd>
                <span>new line</span>
              </div>
              <div className="sm:hidden" />
              <button
                onClick={() => handleStartChat()}
                disabled={!text.trim() || isCreating}
                className={cn(
                  "p-2.5 rounded-sm transition-all cursor-pointer",
                  text.trim() && !isCreating
                    ? "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 shadow-[0_0_14px_hsl(var(--primary)/0.4)] animate-glow-pulse"
                    : "text-[hsl(var(--muted-foreground))] opacity-30",
                )}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Suggestion chips */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-2.5">
          {suggestions.map((s) => (
            <button
              key={s.label}
              onClick={() => handleStartChat(s.prompt)}
              disabled={isCreating}
              className={cn(
                "flex items-center gap-3 p-3.5 rounded-sm text-left transition-all cursor-pointer group",
                "border border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]/80",
                "hover:bg-[hsl(var(--primary))]/5 hover:border-[hsl(var(--primary))]/20 hover:shadow-[0_0_12px_hsl(var(--primary)/0.1)]",
                "disabled:opacity-50 disabled:cursor-not-allowed",
              )}
            >
              <div className="p-2 rounded-sm bg-[hsl(var(--muted))]/50 text-[hsl(var(--muted-foreground))] group-hover:text-[hsl(var(--primary))] group-hover:bg-[hsl(var(--primary))]/10 transition-all shrink-0 border border-[hsl(var(--border))]/30 group-hover:border-[hsl(var(--primary))]/20">
                {s.icon}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-display font-semibold text-[hsl(var(--foreground))]">{s.label}</div>
                <div className="text-xs text-[hsl(var(--muted-foreground))]/60 truncate font-mono">{s.prompt}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
      </div>
    </div>
  )
}
