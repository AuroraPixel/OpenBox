// Tool-chain trace, ported from DEEIX-Chat's message-tool-trace.tsx: one
// collapsed row ("工具调用 · N 次工具调用") over a timeline — a connector rail
// with a dot per call, a fixed label column, and a detail column that renders
// each call's structured output (ToolOutput) instead of a flat text blob.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import type { SubtaskPart, ToolPart } from "@/shared/types/api"
import type { ToolLike } from "../lib/turn-view"
import { describeTool } from "../lib/tool-map"
import { SubagentLine } from "./SubagentLine"
import { ToolOutput } from "./tool/ToolOutput"
import { TraceShell } from "./TraceShell"

interface Step {
  key: string
  label: string
  failed: boolean
  running: boolean
  part: ToolPart | SubtaskPart
}

function stepOf(part: ToolLike, kindLabel: (k: string) => string): Step {
  const label = part.type === "subtask" ? kindLabel("task") : kindLabel(describeTool(part.tool).kindKey)
  return {
    key: part.id,
    label,
    failed: part.status === "error",
    running: part.status === "running" || part.status === "pending",
    part,
  }
}

function ToolChainRows({ steps }: { steps: Step[] }) {
  return (
    <ol className="space-y-0.5">
      {steps.map((step, i) => (
        <li
          key={step.key}
          className="group/row text-xs grid grid-cols-[0.875rem_8rem_minmax(0,1fr)] gap-x-5 gap-y-0.5 leading-5 max-sm:grid-cols-[0.875rem_minmax(0,1fr)] max-sm:gap-x-2"
        >
          <div className="relative flex justify-center">
            {i > 0 && <span className="bg-hair absolute -top-0.5 bottom-1/2 w-px" />}
            {i < steps.length - 1 && <span className="bg-hair absolute top-1/2 -bottom-0.5 w-px" />}
            <span
              className={cn(
                "ring-bg group-hover/row:bg-ink relative z-10 mt-[0.45rem] size-1.5 rounded-full ring-4 transition-colors",
                step.failed ? "bg-danger" : step.running ? "bg-accent animate-pulse-dot" : "bg-n500",
              )}
            />
          </div>
          <div className="min-w-0 max-sm:col-start-2">
            <span
              className={cn(
                "group-hover/row:text-ink block truncate font-medium transition-colors",
                step.failed ? "text-danger" : "text-n700",
              )}
            >
              {step.label}
            </span>
          </div>
          <div className="min-w-0 pb-2 max-sm:col-start-2">
            <ToolOutput part={step.part} />
            {/* A task row is silent for as long as its subagent works, which
                is usually the longest thing in the chain. */}
            {step.part.type === "tool" && step.part.tool === "task" && (
              <SubagentLine part={step.part} inline />
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

interface Props {
  tools: Array<ToolPart | SubtaskPart>
  streaming: boolean
  autoCollapseReady: boolean
}

export function ToolChainTrace({ tools, streaming, autoCollapseReady }: Props) {
  const { t } = useTranslation("chat")
  if (tools.length === 0) return null
  const steps = tools.map((p) => stepOf(p, (k) => t(`kind.${k}`)))
  return (
    <TraceShell
      title={streaming ? t("trace.tool.titleActive") : t("trace.tool.titleDone")}
      subtitle={t("trace.tool.summaryCount", { count: steps.length })}
      streaming={streaming}
      autoCollapseReady={autoCollapseReady}
    >
      <ToolChainRows steps={steps} />
    </TraceShell>
  )
}
