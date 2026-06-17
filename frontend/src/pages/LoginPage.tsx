import { useState, useCallback } from "react"
import { ArrowLeft, Box, Eye, EyeOff, Loader2, Lock, Mail, Monitor, Moon, Sun, User } from "lucide-react"
import { useAuthStore } from "@/stores/auth"
import { useUIStore } from "@/stores/ui"
import { cn } from "@/lib/utils"

const BASE_URL = import.meta.env.VITE_API_URL || ""

interface LoginPageProps {
  onBack?: () => void
}

export function LoginPage({ onBack }: LoginPageProps) {
  const [mode, setMode] = useState<"login" | "register">("login")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)

  const cycleTheme = useCallback(() => {
    const next = theme === "dark" ? "light" : theme === "light" ? "system" : "dark"
    setTheme(next)
  }, [theme, setTheme])

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register"
      const body: Record<string, string> = { username, password }
      if (mode === "register" && email) body.email = email

      const resp = await fetch(`${BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      })

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: "Request failed" }))
        setError(data.detail || `Error ${resp.status}`)
        return
      }

      const data = await resp.json()
      setAuth(data.access_token, data.user)
    } catch {
      setError("Network error. Is the backend running?")
    } finally {
      setLoading(false)
    }
  }, [mode, username, password, email, setAuth])

  const switchMode = useCallback(() => {
    setMode((prev) => (prev === "login" ? "register" : "login"))
    setError("")
  }, [])

  return (
    <div className="min-h-screen flex bg-[hsl(var(--background))]">
      {/* Left: Retro-futurism decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-[hsl(var(--surface-1))]">
        <div className="absolute inset-0 grid-pattern" />
        <div className="absolute top-1/4 left-1/3 w-[400px] h-[400px] bg-[hsl(var(--glow-cyan))]/8 rounded-full blur-[120px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[300px] h-[300px] bg-[hsl(var(--glow-amber))]/6 rounded-full blur-[100px]" />
        <div className="absolute inset-0 scanlines" />

        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/30 flex items-center justify-center glow-cyan">
              <Box className="h-5 w-5 text-[hsl(var(--primary))]" />
            </div>
            <span className="text-xl font-bold font-display">
              Open<span className="text-[hsl(var(--primary))]">Box</span>
            </span>
          </div>

          <div className="max-w-md">
            <h2 className="text-3xl font-bold font-display mb-4 leading-tight text-[hsl(var(--foreground))]">
              Your AI-Powered
              <br />
              <span className="text-[hsl(var(--primary))]" style={{ textShadow: "0 0 30px hsl(185 100% 48% / 0.3)" }}>
                Dev Environment
              </span>
            </h2>
            <p className="text-[hsl(var(--muted-foreground))] leading-relaxed font-mono text-sm">
              Chat with AI agents that can write code, execute commands in secure sandboxes,
              and help you build production-ready applications faster.
            </p>

            <div className="mt-8 space-y-3">
              {[
                { text: "Sandboxed code execution", color: "bg-[hsl(var(--success))]" },
                { text: "Multi-model agent support", color: "bg-[hsl(var(--primary))]" },
                { text: "Extensible skills & MCP", color: "bg-[hsl(var(--accent))]" },
              ].map((item) => (
                <div key={item.text} className="flex items-center gap-3 text-sm text-[hsl(var(--muted-foreground))]">
                  <div className={cn("h-1.5 w-1.5 rounded-sm", item.color)} />
                  <span className="font-mono uppercase tracking-wider text-[10px]">{item.text}</span>
                </div>
              ))}
            </div>
          </div>

          <p className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono uppercase tracking-widest">
            AI-Powered Dev Environment
          </p>
        </div>
      </div>

      {/* Right: Form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="flex items-center justify-between mb-8">
            {onBack ? (
              <button
                onClick={onBack}
                className="flex items-center gap-1.5 text-[10px] text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] transition-colors cursor-pointer font-mono uppercase tracking-wider"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                back to home
              </button>
            ) : <div />}
            <button
              onClick={cycleTheme}
              className="p-2 rounded-sm hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:shadow-[0_0_6px_hsl(var(--primary)/0.2)]"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Moon className="h-4 w-4" /> : theme === "light" ? <Sun className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
            </button>
          </div>

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="h-9 w-9 rounded-sm bg-[hsl(var(--primary))]/10 border border-[hsl(var(--primary))]/30 flex items-center justify-center glow-cyan">
              <Box className="h-5 w-5 text-[hsl(var(--primary))]" />
            </div>
            <span className="text-xl font-bold font-display">
              Open<span className="text-[hsl(var(--primary))]">Box</span>
            </span>
          </div>

          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold font-display tracking-tight mb-1.5 text-[hsl(var(--foreground))]">
              {mode === "login" ? "Welcome back" : "Create account"}
            </h1>
            <p className="text-sm text-[hsl(var(--muted-foreground))] font-mono">
              {mode === "login"
                ? "Sign in to access your AI coding workspace."
                : "Get started with your AI development environment."}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Username
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                  placeholder="Enter your username"
                  className="w-full pl-10 pr-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/50 focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/50 transition-all"
                />
              </div>
            </div>

            {mode === "register" && (
              <div>
                <label htmlFor="email" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                  Email <span className="opacity-50">(optional)</span>
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full pl-10 pr-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/50 focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/50 transition-all"
                  />
                </div>
              </div>
            )}

            <div>
              <label htmlFor="password" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  placeholder="Enter your password"
                  className="w-full pl-10 pr-10 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/50 focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 focus:border-[hsl(var(--primary))]/50 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] transition-colors cursor-pointer"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] font-mono glow-coral">
                <div className="h-1.5 w-1.5 rounded-sm bg-[hsl(var(--destructive))] shrink-0" />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className={cn(
                "w-full flex items-center justify-center gap-2 py-2.5 text-xs font-mono uppercase tracking-widest rounded-sm transition-all cursor-pointer",
                "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
                "hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed",
                "glow-cyan",
              )}
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? "Please wait..." : mode === "login" ? "Sign In" : "Create Account"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-[hsl(var(--muted-foreground))] font-mono">
            {mode === "login" ? (
              <>
                Don't have an account?{" "}
                <button
                  onClick={switchMode}
                  className="text-[hsl(var(--primary))] font-medium hover:underline cursor-pointer"
                >
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  onClick={switchMode}
                  className="text-[hsl(var(--primary))] font-medium hover:underline cursor-pointer"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
