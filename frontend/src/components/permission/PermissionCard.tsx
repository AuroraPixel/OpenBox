import { Shield, Check, X } from "lucide-react"

interface PermissionCardProps {
  tool: string
  action: "once" | "always" | "reject"
}

export function PermissionCard({ tool, action }: PermissionCardProps) {
  const isAllowed = action !== "reject"
  return (
    <div className={`flex items-center gap-2.5 px-3.5 py-2 rounded-sm text-xs border ${
      isAllowed
        ? "bg-[hsl(var(--success))]/8 text-[hsl(var(--success))] border-[hsl(var(--success))]/20 glow-green"
        : "bg-[hsl(var(--destructive))]/8 text-[hsl(var(--destructive))] border-[hsl(var(--destructive))]/20 glow-coral"
    }`}>
      <div className={`h-6 w-6 rounded-sm flex items-center justify-center shrink-0 ${
        isAllowed ? "bg-[hsl(var(--success))]/15" : "bg-[hsl(var(--destructive))]/15"
      }`}>
        <Shield className="h-3 w-3" />
      </div>
      <span className="font-mono font-medium">{tool}</span>
      <div className="ml-auto flex items-center gap-1.5">
        {isAllowed ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
        <span className="text-[10px] font-mono uppercase tracking-wider opacity-80">{action === "always" ? "Always allowed" : action === "once" ? "Allowed once" : "Rejected"}</span>
      </div>
    </div>
  )
}
