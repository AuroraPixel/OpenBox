import { useCallback } from "react"
import {
  ArrowRight,
  Box,
  Code2,
  Cpu,
  FileSearch,
  GitBranch,
  Layers,
  Lock,
  MessageSquare,
  Monitor,
  Moon,
  Puzzle,
  Shield,
  Sun,
  Terminal,
  Zap,
} from "lucide-react"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"

interface LandingPageProps {
  onLogin: () => void
}

const features = [
  {
    icon: <MessageSquare className="h-5 w-5" />,
    title: "AI Chat",
    description: "Conversational coding with real-time streaming, slash commands, and file mentions.",
    borderColor: "border-[hsl(var(--primary))]/20 hover:border-[hsl(var(--primary))]/40",
    iconColor: "text-[hsl(var(--primary))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--primary)/0.1)]",
  },
  {
    icon: <Terminal className="h-5 w-5" />,
    title: "Sandboxed Exec",
    description: "Secure container-based environments for running code, testing, and debugging.",
    borderColor: "border-[hsl(var(--success))]/20 hover:border-[hsl(var(--success))]/40",
    iconColor: "text-[hsl(var(--success))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--success)/0.1)]",
  },
  {
    icon: <Code2 className="h-5 w-5" />,
    title: "Smart Editing",
    description: "AI-powered file editing with diff preview, code generation, and refactoring.",
    borderColor: "border-[hsl(var(--accent))]/20 hover:border-[hsl(var(--accent))]/40",
    iconColor: "text-[hsl(var(--accent))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--accent)/0.1)]",
  },
  {
    icon: <Puzzle className="h-5 w-5" />,
    title: "Skills System",
    description: "Install custom skills to extend AI capabilities for your specific workflow.",
    borderColor: "border-[hsl(var(--destructive))]/20 hover:border-[hsl(var(--destructive))]/40",
    iconColor: "text-[hsl(var(--destructive))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--destructive)/0.1)]",
  },
  {
    icon: <Layers className="h-5 w-5" />,
    title: "MCP Servers",
    description: "Connect to Model Context Protocol servers for tools, data, and external services.",
    borderColor: "border-[hsl(var(--primary))]/20 hover:border-[hsl(var(--primary))]/40",
    iconColor: "text-[hsl(var(--primary))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--primary)/0.1)]",
  },
  {
    icon: <Shield className="h-5 w-5" />,
    title: "Permissions",
    description: "Fine-grained permission system for tool execution with approval workflows.",
    borderColor: "border-[hsl(var(--accent))]/20 hover:border-[hsl(var(--accent))]/40",
    iconColor: "text-[hsl(var(--accent))]",
    glowClass: "hover:shadow-[0_0_20px_hsl(var(--accent)/0.1)]",
  },
]

const highlights = [
  { icon: <Cpu className="h-3.5 w-3.5" />, label: "Multi-Model", color: "text-[hsl(var(--primary))] border-[hsl(var(--primary))]/20" },
  { icon: <GitBranch className="h-3.5 w-3.5" />, label: "Agents", color: "text-[hsl(var(--accent))] border-[hsl(var(--accent))]/20" },
  { icon: <FileSearch className="h-3.5 w-3.5" />, label: "Analysis", color: "text-[hsl(var(--success))] border-[hsl(var(--success))]/20" },
  { icon: <Lock className="h-3.5 w-3.5" />, label: "Secure", color: "text-[hsl(var(--destructive))] border-[hsl(var(--destructive))]/20" },
]

export function LandingPage({ onLogin }: LandingPageProps) {
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)

  const cycleTheme = useCallback(() => {
    const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark"
    setTheme(next)
  }, [theme, setTheme])

  const handleGetStarted = useCallback(() => {
    onLogin()
  }, [onLogin])

  return (
    <div className="min-h-screen bg-[hsl(var(--background))] overflow-y-auto">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 backdrop-blur-xl bg-[hsl(var(--background))]/80 border-b border-[hsl(var(--border))]">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/30 flex items-center justify-center glow-cyan">
              <Box className="h-4 w-4 text-[hsl(var(--primary))]" />
            </div>
            <span className="text-lg font-bold font-display tracking-tight text-[hsl(var(--foreground))]">
              Open<span className="text-[hsl(var(--primary))]">Box</span>
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              onClick={cycleTheme}
              className="p-2 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:shadow-[0_0_6px_hsl(var(--primary)/0.2)]"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Moon className="h-4 w-4" /> : theme === "light" ? <Sun className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
            </button>
            <button
              onClick={handleGetStarted}
              className="flex items-center gap-2 px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-all cursor-pointer glow-cyan"
            >
              Sign In
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-24 pb-20 px-6 overflow-hidden scanlines">
        <div className="absolute inset-0 -z-10 grid-pattern" />
        <div className="absolute inset-0 -z-10">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-[hsl(var(--glow-cyan))]/5 rounded-full blur-[120px]" />
          <div className="absolute top-40 left-1/4 w-[300px] h-[300px] bg-[hsl(var(--glow-amber))]/4 rounded-full blur-[100px]" />
          <div className="absolute top-60 right-1/4 w-[250px] h-[250px] bg-[hsl(var(--glow-coral))]/3 rounded-full blur-[100px]" />
        </div>

        <div className="relative max-w-4xl mx-auto text-center">
          {/* Pixel badge */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-sm border border-[hsl(var(--primary))]/20 bg-[hsl(var(--primary))]/5 text-[10px] font-mono uppercase tracking-widest text-[hsl(var(--primary))] mb-8 animate-flicker">
            <Zap className="h-3 w-3" />
            AI-Powered Dev Environment
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold font-display tracking-tight mb-6 leading-[1.05] text-[hsl(var(--foreground))]">
            Build Faster with
            <br />
            <span className="text-[hsl(var(--primary))]" style={{ textShadow: "0 0 40px hsl(185 100% 48% / 0.3)" }}>
              AI Coding Agents
            </span>
          </h1>

          <p className="text-base text-[hsl(var(--muted-foreground))] max-w-2xl mx-auto mb-10 leading-relaxed font-mono">
            OpenBox gives you a complete AI coding environment with sandboxed execution,
            intelligent file editing, and extensible agent workflows.
          </p>

          {/* CTA */}
          <div className="flex items-center justify-center gap-4 mb-14">
            <button
              onClick={handleGetStarted}
              className="flex items-center gap-2 px-7 py-3.5 text-xs font-mono uppercase tracking-widest rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-all cursor-pointer animate-glow-pulse"
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          {/* Highlight badges */}
          <div className="flex flex-wrap items-center justify-center gap-3">
            {highlights.map((h) => (
              <div
                key={h.label}
                className={cn(
                  "flex items-center gap-2 px-3.5 py-2 rounded-sm border bg-[hsl(var(--card))]/80 text-[10px] font-mono uppercase tracking-wider",
                  h.color,
                )}
              >
                {h.icon}
                {h.label}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Terminal Preview */}
      <section className="px-6 pb-20">
        <div className="max-w-4xl mx-auto">
          <div className="rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--card))] overflow-hidden glow-cyan">
            <div className="flex items-center gap-3 px-4 py-2.5 bg-[hsl(var(--surface-2))] border-b border-[hsl(var(--border))]">
              <div className="flex gap-1.5">
                <div className="h-3 w-3 rounded-sm bg-[hsl(var(--destructive))]/80" />
                <div className="h-3 w-3 rounded-sm bg-[hsl(var(--accent))]/80" />
                <div className="h-3 w-3 rounded-sm bg-[hsl(var(--success))]/80" />
              </div>
              <span className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-widest ml-1">
                openbox://session
              </span>
            </div>
            <div className="p-5 font-mono text-sm space-y-3 bg-[hsl(var(--terminal-bg))]">
              <div className="flex items-start gap-2">
                <span className="text-[hsl(var(--primary))] shrink-0">&gt;_</span>
                <span className="text-[hsl(var(--foreground))]">Build a REST API with user authentication and JWT tokens</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[hsl(var(--accent))] shrink-0">ai</span>
                <div className="space-y-1.5">
                  <span className="text-[hsl(var(--muted-foreground))]">Creating a complete auth system. Setting up project structure...</span>
                  <div className="mt-2 pl-3 border-l-2 border-[hsl(var(--primary))]/30 space-y-1">
                    <div className="text-[hsl(var(--success))]/80 text-xs">
                      <span className="text-[hsl(var(--muted-foreground))]">[tool]</span> Creating src/auth/controller.ts
                    </div>
                    <div className="text-[hsl(var(--success))]/80 text-xs">
                      <span className="text-[hsl(var(--muted-foreground))]">[tool]</span> Creating src/auth/middleware.ts
                    </div>
                    <div className="text-[hsl(var(--success))]/80 text-xs">
                      <span className="text-[hsl(var(--muted-foreground))]">[tool]</span> Running npm test — 12 tests passed
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
                <div className="h-1.5 w-1.5 rounded-sm bg-[hsl(var(--success))] animate-pulse-dot shadow-[0_0_6px_hsl(var(--success))]" />
                <span className="font-mono uppercase tracking-wider text-[10px]">completed in 23s — 5 files, all tests pass</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="px-6 pb-24">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold font-display tracking-tight mb-4 text-[hsl(var(--foreground))]">
              Everything to <span className="text-[hsl(var(--accent))]">Ship Faster</span>
            </h2>
            <p className="text-[hsl(var(--muted-foreground))] max-w-xl mx-auto font-mono text-sm">
              A complete dev environment powered by AI agents with sandboxed execution and extensible capabilities.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((feature) => (
              <div
                key={feature.title}
                className={cn(
                  "group relative rounded-sm border p-5 transition-all bg-[hsl(var(--card))]/80",
                  feature.borderColor,
                  feature.glowClass,
                )}
              >
                <div className={cn(
                  "inline-flex items-center justify-center h-10 w-10 rounded-sm mb-4",
                  "bg-[hsl(var(--muted))] border border-[hsl(var(--border))]",
                )}>
                  <span className={feature.iconColor}>{feature.icon}</span>
                </div>
                <h3 className="font-display font-semibold text-sm mb-1.5 uppercase tracking-wider text-[hsl(var(--foreground))]">{feature.title}</h3>
                <p className="text-xs text-[hsl(var(--muted-foreground))] leading-relaxed">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="px-6 pb-24">
        <div className="max-w-2xl mx-auto text-center">
          <div className="rounded-sm border border-[hsl(var(--primary))]/20 bg-[hsl(var(--card))] p-12 relative overflow-hidden">
            <div className="absolute inset-0 grid-pattern opacity-50" />
            <div className="relative">
              <h2 className="text-2xl font-bold font-display mb-3 text-[hsl(var(--foreground))]">
                Ready to <span className="text-[hsl(var(--primary))]">Get Started</span>?
              </h2>
              <p className="text-[hsl(var(--muted-foreground))] mb-8 text-sm font-mono">
                Sign in to access your AI coding environment.
              </p>
              <button
                onClick={handleGetStarted}
                className="inline-flex items-center gap-2 px-7 py-3 text-xs font-mono uppercase tracking-widest rounded-sm bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 transition-all cursor-pointer glow-cyan"
              >
                Sign In to OpenBox
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[hsl(var(--border))] px-6 py-6">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Box className="h-4 w-4 text-[hsl(var(--primary))]" />
            <span className="text-xs font-display text-[hsl(var(--muted-foreground))]">OpenBox</span>
          </div>
          <span className="text-[10px] font-mono uppercase tracking-widest text-[hsl(var(--muted-foreground))]">AI-Powered Dev</span>
        </div>
      </footer>
    </div>
  )
}
