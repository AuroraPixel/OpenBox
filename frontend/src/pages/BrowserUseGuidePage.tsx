import { useEffect, useRef, useState } from "react"
import { ArrowLeft, Download, MonitorSmartphone, X } from "lucide-react"
import { cn } from "@/lib/utils"

const steps = [
  {
    id: "step-1",
    title: "Use Incognito Mode",
    description: "Open OpenAgent in Chrome's Incognito mode. This ensures the Dev Browser extension won't interfere with the application's own session.",
    image: "/downloads/step-01.png",
  },
  {
    id: "step-2",
    title: "Open the Browser Tab",
    description: "Start or open any chat session, then click the \"Browser\" tab in the top navigation bar.",
    image: "/downloads/step-02.png",
  },
  {
    id: "step-3",
    title: "Download the Extension",
    description: "Click the \"Download Extension\" button in the banner to download the extension zip file. Extract (unzip) the downloaded file to a folder on your computer.",
    image: "/downloads/step-03.png",
    action: {
      label: "Download Extension",
      href: "/downloads/openbox-dev-browser.zip",
      download: true,
    },
  },
  {
    id: "step-4",
    title: "Install in Chrome",
    description: "Open a normal (non-incognito) Chrome window. Navigate to chrome://extensions/ in the address bar, enable \"Developer mode\" (top-right toggle), then click \"Load unpacked\" (top-left).",
    image: "/downloads/step-04.png",
    note: "You need to type chrome://extensions/ manually in your browser address bar.",
  },
  {
    id: "step-5",
    title: "Select Extension Folder",
    description: "In the file picker dialog, navigate to and select the folder you extracted from the zip file (e.g. \"openbox-dev-browser\"), then click \"Select Folder\".",
    image: "/downloads/step-05.png",
  },
  {
    id: "step-6",
    title: "Installation Complete",
    description: "The OpenAgent Browser extension should now appear in your extensions list with the toggle enabled.",
    image: "/downloads/step-06.png",
  },
  {
    id: "step-7",
    title: "Pin to Toolbar",
    description: "Click the puzzle piece icon in Chrome's toolbar, find \"OpenAgent Browser\" and click the pin icon to keep it visible for easy access.",
    image: "/downloads/step-07.png",
  },
  {
    id: "step-8",
    title: "Enable Dev Browser",
    description: "Go back to the OpenAgent application (in Incognito mode). On the Browser tab, click \"Enable Dev Browser\", then confirm. The relay server will start.",
    image: "/downloads/step-09.png",
  },
  {
    id: "step-9",
    title: "Connect the Extension",
    description: "Click the OpenAgent Browser extension icon in the normal Chrome window. Make sure you are logged in (the extension auto-detects your login). Toggle to \"Active\" and wait until it shows \"Connected to relay\" — no manual configuration needed.",
    image: "/downloads/step-10.png",
  },
  {
    id: "step-10",
    title: "Start Browser Automation",
    description: "Go back to the chat window and ask the agent to use the browser. For example: \"Use the browser to open baidu.com\". The agent will load the dev-browser skill, start the relay, and control your Chrome browser.",
    image: "/downloads/step-11.png",
  },
]

export function BrowserUseGuidePage() {
  const [activeId, setActiveId] = useState(steps[0].id)
  const [lightbox, setLightbox] = useState<string | null>(null)
  const contentRef = useRef<HTMLDivElement>(null)

  // Close lightbox on Escape
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setLightbox(null) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [lightbox])

  // Track which step is in view via IntersectionObserver
  useEffect(() => {
    const container = contentRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
          }
        }
      },
      { root: container, rootMargin: "-20% 0px -70% 0px", threshold: 0 }
    )

    for (const step of steps) {
      const el = document.getElementById(step.id)
      if (el) observer.observe(el)
    }

    return () => observer.disconnect()
  }, [])

  const scrollTo = (id: string) => {
    const el = document.getElementById(id)
    el?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <div className="h-screen flex bg-[hsl(var(--background))]">
      {/* Main content — scrollable */}
      <div ref={contentRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-10">
          {/* Header */}
          <div className="mb-10">
            <a
              href="/#"
              className="inline-flex items-center gap-1.5 text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] transition-colors mb-6"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to App
            </a>
            <div className="flex items-center gap-4">
              <div className="h-14 w-14 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/20 flex items-center justify-center glow-cyan">
                <MonitorSmartphone className="h-7 w-7 text-[hsl(var(--primary))]" />
              </div>
              <div>
                <h1 className="text-2xl font-display font-bold text-[hsl(var(--foreground))]">
                  Browser Use Setup Guide
                </h1>
                <p className="text-sm text-[hsl(var(--muted-foreground))] font-mono mt-1">
                  Let the AI agent control your Chrome browser for web automation
                </p>
              </div>
            </div>
          </div>

          {/* Platform note */}
          <div className="mb-8 px-5 py-4 rounded-sm border border-[hsl(var(--accent))]/20 bg-[hsl(var(--accent))]/5">
            <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono leading-relaxed">
              <span className="text-[hsl(var(--accent))] font-semibold">Note:</span> This guide demonstrates the setup on Windows. The steps are identical on <strong className="text-[hsl(var(--foreground))]">macOS</strong> and <strong className="text-[hsl(var(--foreground))]">Linux</strong> — just follow the same process in your Chrome browser.
            </p>
          </div>

          {/* Steps */}
          <div className="space-y-12">
            {steps.map((step, index) => (
              <article
                key={step.id}
                id={step.id}
                className="scroll-mt-6 rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden"
              >
                {/* Step header */}
                <div className="px-6 py-5 border-b border-[hsl(var(--border))]/50">
                  <div className="flex items-center gap-3">
                    <span className="flex items-center justify-center h-7 w-7 rounded-full bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] text-xs font-mono font-bold shrink-0">
                      {index + 1}
                    </span>
                    <h2 className="text-sm font-mono uppercase tracking-wider font-semibold text-[hsl(var(--foreground))]">
                      {step.title}
                    </h2>
                  </div>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono mt-3 ml-10 leading-relaxed">
                    {step.description}
                  </p>
                  {step.note && (
                    <p className="text-[11px] text-[hsl(var(--accent))] font-mono mt-2 ml-10">
                      Note: {step.note}
                    </p>
                  )}
                  {step.action && (
                    <div className="mt-3 ml-10">
                      <a
                        href={step.action.href}
                        download={step.action.download ? "openbox-dev-browser.zip" : undefined}
                        className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-opacity cursor-pointer glow-cyan"
                      >
                        <Download className="h-3.5 w-3.5" />
                        {step.action.label}
                      </a>
                    </div>
                  )}
                </div>

                {/* Step image — click to enlarge */}
                <div
                  className="bg-black/20 cursor-zoom-in"
                  onClick={() => setLightbox(step.image)}
                >
                  <img
                    src={step.image}
                    alt={`Step ${index + 1}: ${step.title}`}
                    className="w-full h-auto hover:opacity-90 transition-opacity"
                    loading="lazy"
                  />
                </div>
              </article>
            ))}
          </div>

          {/* Footer */}
          <div className="mt-12 mb-10 p-6 rounded-sm border border-[hsl(var(--success))]/20 bg-[hsl(var(--success))]/5">
            <div className="flex items-center gap-3">
              <MonitorSmartphone className="h-5 w-5 text-[hsl(var(--success))]" />
              <div>
                <p className="text-sm font-mono font-semibold text-[hsl(var(--success))]">
                  Setup Complete
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] font-mono mt-1">
                  You can now ask the agent to browse websites, fill forms, take screenshots, and automate web tasks through your Chrome browser.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right TOC sidebar */}
      <aside className="w-56 shrink-0 border-l border-[hsl(var(--border))]/50 bg-[hsl(var(--card))]/50 overflow-y-auto hidden lg:block">
        <div className="sticky top-0 px-4 py-6">
          <p className="text-[10px] font-mono uppercase tracking-widest text-[hsl(var(--muted-foreground))] mb-4">
            On This Page
          </p>
          <nav className="space-y-0.5">
            {steps.map((step, index) => (
              <button
                key={step.id}
                onClick={() => scrollTo(step.id)}
                className={cn(
                  "w-full text-left flex items-center gap-2 px-2.5 py-1.5 rounded-sm text-[11px] font-mono transition-all cursor-pointer",
                  activeId === step.id
                    ? "text-[hsl(var(--primary))] bg-[hsl(var(--primary))]/10 border-l-2 border-[hsl(var(--primary))]"
                    : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] hover:bg-[hsl(var(--muted))]/60",
                )}
              >
                <span className={cn(
                  "w-4 text-center shrink-0 tabular-nums",
                  activeId === step.id ? "font-bold" : "",
                )}>
                  {index + 1}
                </span>
                <span className="truncate">{step.title}</span>
              </button>
            ))}
          </nav>
        </div>
      </aside>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm cursor-zoom-out"
          onClick={() => setLightbox(null)}
        >
          <button
            onClick={() => setLightbox(null)}
            className="absolute top-4 right-4 p-2 rounded-sm bg-white/10 text-white hover:bg-white/20 transition-colors cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
          <img
            src={lightbox}
            alt="Enlarged view"
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-sm shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  )
}
