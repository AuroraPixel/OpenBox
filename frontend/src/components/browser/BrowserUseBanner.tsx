import { useState } from "react"
import { MonitorSmartphone, X, ExternalLink } from "lucide-react"

const DISMISSED_KEY = "browserUseBannerDismissed"

export function BrowserUseBanner() {
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem(DISMISSED_KEY) === "1" } catch { return false }
  })

  if (dismissed) return null

  const handleDismiss = () => {
    setDismissed(true)
    try { sessionStorage.setItem(DISMISSED_KEY, "1") } catch {}
  }

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-[hsl(var(--primary))]/5 border-b border-[hsl(var(--primary))]/15 shrink-0">
      <MonitorSmartphone className="h-3.5 w-3.5 text-[hsl(var(--primary))] shrink-0" />
      <span className="text-xs font-mono text-[hsl(var(--muted-foreground))] flex-1">
        Browser Use: Let the agent control your Chrome browser
      </span>
      <a
        href="/#/browser-use-guide"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 px-3 py-1 text-[10px] font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--primary))]/30 text-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/10 transition-all cursor-pointer shrink-0"
      >
        <ExternalLink className="h-3 w-3" />
        Setup Guide
      </a>
      <button
        onClick={handleDismiss}
        className="p-1 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))] transition-all cursor-pointer shrink-0"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}
