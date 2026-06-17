import { CheckCircle2, Circle, Loader2, ListTodo } from "lucide-react"
import { Progress } from "@/components/ui/Progress"
import { useQuery } from "@tanstack/react-query"
import { useSessionStore } from "@/stores/session"
import { api } from "@/services/api"

interface TodoPanelProps {
  sessionId: string
  fallbackEmpty?: boolean
}

export function TodoPanel({ sessionId, fallbackEmpty }: TodoPanelProps) {
  const todoVersion = useSessionStore((s) => s.todoVersion)
  const resolvedSessionId = useSessionStore((s) => s.resolveSessionId(sessionId))

  const { data } = useQuery({
    queryKey: ["todo", resolvedSessionId, todoVersion],
    queryFn: () => api.getTodo(resolvedSessionId),
    enabled: !resolvedSessionId.startsWith("mock-"),
  })

  const items = data?.items || []

  if (items.length === 0) {
    if (fallbackEmpty) {
      return (
        <div className="flex flex-col items-center justify-center py-12 px-4 text-center grid-pattern">
          <div className="h-12 w-12 rounded-sm bg-[hsl(var(--muted))]/30 flex items-center justify-center mb-3">
            <Circle className="h-5 w-5 text-[hsl(var(--muted-foreground))]/40" />
          </div>
          <p className="text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No active tasks for this session</p>
        </div>
      )
    }
    return null
  }

  const completed = items.filter((i) => i.status === "completed").length
  const total = items.length

  return (
    <div className="border-t border-[hsl(var(--border))]/50">
      <div className="px-4 py-3">
        <h3 className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-3 flex items-center gap-2">
          <div className="h-5 w-5 rounded-sm bg-[hsl(var(--success))]/15 flex items-center justify-center glow-green">
            <ListTodo className="h-3 w-3 text-[hsl(var(--success))]" />
          </div>
          Todo
        </h3>
        <div className="space-y-1.5">
          {items.map((item) => (
            <div key={item.id} className="flex items-start gap-2.5 text-xs group">
              <TodoIcon status={item.status} />
              <span className={item.status === "completed" ? "line-through text-[hsl(var(--muted-foreground))]/50 font-mono" : "leading-relaxed font-mono"}>
                {item.subject}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-3">
          <div className="text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5 tabular-nums">
            {completed}/{total} completed
          </div>
          <Progress value={completed} max={total} />
        </div>
      </div>
    </div>
  )
}

function TodoIcon({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return <CheckCircle2 className="h-3.5 w-3.5 text-[hsl(var(--success))] shrink-0 mt-0.5 glow-green" />
    case "in_progress":
      return <Loader2 className="h-3.5 w-3.5 text-[hsl(var(--primary))] animate-spin shrink-0 mt-0.5 glow-cyan" />
    default:
      return <Circle className="h-3.5 w-3.5 text-[hsl(var(--muted-foreground))]/40 shrink-0 mt-0.5" />
  }
}
