import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitBranch } from "lucide-react"
import { DiffFile } from "./DiffFile"
import { DiffSummary } from "./DiffSummary"
import { Spinner } from "@/components/ui/Spinner"
import { api } from "@/services/api"
import { useSessionStore } from "@/stores/session"
import type { DiffEntry } from "@/types"

interface DiffViewProps {
  entries?: DiffEntry[]
  sessionId: string
}

export function DiffView({ entries: propEntries, sessionId }: DiffViewProps) {
  const [viewMode, setViewMode] = useState<"unified" | "split">("unified")
  const diffVersion = useSessionStore((s) => s.diffVersion)
  const resolvedSessionId = useSessionStore((s) => s.resolveSessionId(sessionId))

  // Fetch from API if not provided as props
  const { data: fetchedEntries, isLoading } = useQuery({
    queryKey: ["diff", resolvedSessionId, diffVersion],
    queryFn: () => api.getSessionDiff(resolvedSessionId),
    enabled: !propEntries && !resolvedSessionId.startsWith("mock-"),
  })

  const entries = propEntries || fetchedEntries || []

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <div className="h-full flex items-center justify-center grid-pattern">
        <div className="text-center space-y-3">
          <div className="h-16 w-16 rounded-sm bg-[hsl(var(--primary))]/10 flex items-center justify-center mx-auto glow-cyan">
            <GitBranch className="h-8 w-8 text-[hsl(var(--primary))]/40" />
          </div>
          <p className="text-sm font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))]">No changes in this session</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <DiffSummary entries={entries} viewMode={viewMode} onViewModeChange={setViewMode} />
      <div className="p-4 space-y-3">
        {entries.map((entry) => (
          <DiffFile key={entry.path} entry={entry} viewMode={viewMode} />
        ))}
      </div>
    </div>
  )
}
