// One line under a `task` row saying what the subagent is doing.
//
// opencode shows the same thing in its TUI — "↳ Bash npm test", or a count
// when there is no title yet — because a task row that only says "running"
// tells you nothing for however many minutes the child takes.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { formatDuration } from "@/shared/lib/format"
import type { ToolPart } from "@/shared/types/api"
import { useSubagentProgress } from "../hooks/useSubagentProgress"
import { describeTool, toolTarget } from "../lib/tool-map"

export function SubagentLine({ part, inline }: { part: ToolPart; inline?: boolean }) {
  const { t } = useTranslation("chat")
  const progress = useSubagentProgress(part)
  const running = part.status === "running" || part.status === "pending"

  // Nothing to add before the child has reported anything: the row above
  // already says the call is running.
  if (!progress.sessionId || progress.toolCount === 0) return null

  const { current } = progress
  const detail =
    running && current
      ? `${t(`kind.${describeTool(current.tool).kindKey}`)} ${toolTarget(current)}`
      : t("subagent.summary", {
          count: progress.toolCount,
          duration: formatDuration(progress.seconds),
        })

  return (
    <div className={inline ? "pt-0.5" : "ps-9 pb-1.5"}>
      <span
        className={cn(
          "text-n600 inline-flex min-w-0 max-w-full items-baseline gap-1.5 text-xs",
          running && "text-shimmer",
        )}
      >
        <span aria-hidden className="text-n500 flex-none">
          ↳
        </span>
        <span className="truncate font-mono">{detail}</span>
      </span>
    </div>
  )
}
