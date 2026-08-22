// The calls made while one task was running.
//
// Same information as the flat tool chain, laid out as rows that read at a
// glance: what kind of call, what it was aimed at, and how it ended. A row
// opens to the same structured detail the chain shows, so nothing is lost by
// being inside the card.
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronRight } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { formatDuration } from "@/shared/lib/format"
import type { SubtaskPart, ToolPart } from "@/shared/types/api"
import { describeTool, toneBgClass, toneFgClass, toolTarget } from "../lib/tool-map"
import { parseExitCode } from "../lib/tool-parse"
import { toolDuration, type ToolLike } from "../lib/turn-view"
import { ToolOutput } from "./tool/ToolOutput"

function Row({ part }: { part: ToolPart | SubtaskPart }) {
  const { t } = useTranslation("chat")
  const [open, setOpen] = useState(false)

  const subtask = part.type === "subtask"
  const glyph = subtask ? null : describeTool(part.tool)
  const label = subtask ? t("kind.task") : t(`kind.${glyph!.kindKey}`)
  const target = subtask ? part.description : toolTarget(part)

  const running = part.status === "running" || part.status === "pending"
  const failed = part.status === "error"
  const seconds = toolDuration(part)
  const exit = part.type === "tool" ? parseExitCode(part.metadata) : null

  // The right-hand column: how it went, in the fewest words that still say
  // something. A running call has no duration yet, so it says so instead.
  const meta = running
    ? t("toolMeta.running")
    : [
        seconds !== null ? formatDuration(seconds) : null,
        exit !== null ? t("toolMeta.exit", { code: exit }) : failed ? t("toolMeta.failed") : null,
      ]
        .filter(Boolean)
        .join(" · ")

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group/row flex w-full items-center gap-3 rounded-lg py-1.5 text-start"
      >
        <span
          className={cn(
            "flex size-6 flex-none items-center justify-center rounded-full text-xs",
            subtask ? toneBgClass.grey : toneBgClass[glyph!.tone],
            subtask ? toneFgClass.grey : toneFgClass[glyph!.tone],
            failed && "text-danger",
          )}
        >
          {subtask ? "◆" : glyph!.glyph}
        </span>
        <span className="text-n700 group-hover/row:text-ink w-20 flex-none truncate text-sm transition-colors max-sm:hidden">
          {label}
        </span>
        <span
          className={cn(
            "min-w-0 flex-1 truncate font-mono text-sm transition-colors",
            failed ? "text-danger" : "text-n800 group-hover/row:text-ink",
          )}
        >
          {target}
        </span>
        <span
          className={cn(
            "text-n600 shrink-0 text-xs tabular-nums max-sm:hidden",
            running && "text-shimmer",
          )}
        >
          {meta}
        </span>
        <ChevronRight
          className={cn(
            "text-n500 size-3.5 shrink-0 transition-transform duration-200",
            open && "rotate-90",
          )}
        />
      </button>
      <div className="fold" data-open={open}>
        <div>
          <div className="ps-9 pb-2">
            <ToolOutput part={part} />
          </div>
        </div>
      </div>
    </li>
  )
}

export function TaskToolRows({ tools }: { tools: ToolLike[] }) {
  if (tools.length === 0) return null
  return (
    <ul className="flex flex-col">
      {tools.map((part) => (
        <Row key={part.id} part={part} />
      ))}
    </ul>
  )
}
