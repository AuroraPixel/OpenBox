// Structured detail column for one tool call. Dispatches on the tool's layout
// (resolveToolLayout) and composes request/response blocks from the primitives.
// Research tools (web_search / web_fetch) get first-class source rendering.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { emitAppEvent } from "@/shared/events/bus"
import type { ToolPart, ToolStatus, SubtaskPart } from "@/shared/types/api"
import { resolveToolLayout } from "../../lib/tool-map"
import {
  isTruncated,
  parseEdits,
  parseExitCode,
  parseSearchResults,
  parseSearchUrls,
  stripLineNumbers,
} from "../../lib/tool-parse"
import { ToolDetailText, ToolMiniLabel, ToolPre, ToolSourceLinks } from "./ToolPrimitives"
import { DiffRows } from "../DiffRows"
import { editPreview } from "../../lib/diff-preview"

interface LayoutProps {
  part: ToolPart
  failed: boolean
}

function strv(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

function safeStringify(input: Record<string, unknown>): string {
  try {
    return JSON.stringify(input, null, 2)
  } catch {
    return ""
  }
}

function Wrap({ failed, children }: { failed?: boolean; children: React.ReactNode }) {
  return <div className={cn("text-n700 space-y-2", failed && "text-danger")}>{children}</div>
}

function StatusLine({ status }: { status: ToolStatus }) {
  const { t } = useTranslation("chat")
  const running = status === "running" || status === "pending"
  const text = running
    ? t("toolStatus.running")
    : status === "error"
      ? t("toolStatus.failed")
      : t("toolStatus.completed")
  return <div className={cn("text-2xs text-n600", running && "text-shimmer")}>{text}</div>
}


function SearchOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const input = part.input ?? {}
  const query = strv(input.query) || strv(part.metadata?.query)
  const action = strv(input.action) || strv(input.type)
  const results = parseSearchResults(part.metadata)
  const urls = results.length > 0 ? results.map((r) => r.url) : parseSearchUrls(part.output)
  const responseLabel = failed ? t("toolDetail.error") : t("toolDetail.response")
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {(query || (action && action !== query)) && (
        <div>
          <ToolMiniLabel>{t("toolDetail.request")}</ToolMiniLabel>
          <div className="space-y-1">
            {query && (
              <div className="break-words">
                {t("toolDetail.query")}: {query}
              </div>
            )}
            {action && action !== query && (
              <div className="break-words">
                {t("toolDetail.action")}: {action}
              </div>
            )}
          </div>
        </div>
      )}
      {urls.length > 0 || results.length > 0 ? (
        <div>
          <ToolMiniLabel>{responseLabel}</ToolMiniLabel>
          <ToolSourceLinks urls={urls} />
          {results.length > 0 && (
            <div className="mt-2 space-y-2">
              {results.map((r, i) => (
                <div key={`${r.url}-${i}`}>
                  {r.title && <div className="text-n800 text-xs font-medium">{r.title}</div>}
                  {r.snippet && <div className="text-2xs text-n600 line-clamp-2">{r.snippet}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : part.output ? (
        <div>
          <ToolMiniLabel>{responseLabel}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{failed ? part.error || part.output : part.output}</ToolDetailText>
        </div>
      ) : null}
    </Wrap>
  )
}

function FetchOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const url = strv(part.input?.url)
  const body = failed ? part.error || part.output || "" : part.output || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {url && (
        <div>
          <ToolMiniLabel>{t("toolDetail.request")}</ToolMiniLabel>
          <ToolSourceLinks urls={[url]} />
        </div>
      )}
      {body && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.response")}</ToolMiniLabel>
          <ToolPre failed={failed}>{body}</ToolPre>
          {isTruncated(part.metadata) && <div className="text-2xs text-n600 mt-1">{t("toolDetail.truncated")}</div>}
        </div>
      )}
    </Wrap>
  )
}

function ShellOutput({ part }: LayoutProps) {
  const { t } = useTranslation("chat")
  const command = strv(part.input?.command)
  const exitCode = parseExitCode(part.metadata)
  const failed = part.status === "error" || Boolean(part.error?.trim()) || (exitCode !== null && exitCode !== 0)
  const output = part.output || part.error || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {command && (
        <div>
          <ToolMiniLabel>{t("toolDetail.command")}</ToolMiniLabel>
          <ToolPre>{command}</ToolPre>
        </div>
      )}
      {output && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.output")}</ToolMiniLabel>
          <ToolPre failed={failed}>{output}</ToolPre>
        </div>
      )}
      {exitCode !== null && exitCode !== 0 && (
        <div className="text-2xs text-danger">
          {t("toolDetail.exitCode")}: {exitCode}
        </div>
      )}
    </Wrap>
  )
}

function FileOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const tool = part.tool.toLowerCase()
  const input = part.input ?? {}
  const path = strv(input.file_path) || strv(input.path)
  const edits = parseEdits(input)
  const content =
    tool === "read"
      ? stripLineNumbers(part.output || "")
      : tool === "write"
        ? strv(input.content) || part.output || ""
        : strv(input.patch) || part.output || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {path && <div className="text-n800 font-mono text-xs break-words">{path}</div>}
      {edits.length > 0 ? (
        <div className="space-y-2">
          <ToolMiniLabel>{t("toolDetail.diff")}</ToolMiniLabel>
          {edits.map((edit, i) => {
            const preview = editPreview(edit.oldString, edit.newString)
            const rows = <DiffRows rows={preview.rows} hidden={preview.hiddenChanges} />
            // These rows look exactly like the turn's change card, so they open
            // review the same way — anything else reads as a dead click.
            return path ? (
              <button
                key={i}
                type="button"
                onClick={() => emitAppEvent("workbench.open", { kind: "review", file: path })}
                title={t("diff.openReview")}
                className="border-hair hover:border-n400 block w-full overflow-hidden rounded-lg border text-start transition-colors"
              >
                {rows}
              </button>
            ) : (
              <div key={i} className="border-hair overflow-hidden rounded-lg border">
                {rows}
              </div>
            )
          })}
        </div>
      ) : content ? (
        <div>
          <ToolMiniLabel>{t("toolDetail.content")}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{content}</ToolDetailText>
        </div>
      ) : null}
      {failed && part.error && (
        <div>
          <ToolMiniLabel>{t("toolDetail.error")}</ToolMiniLabel>
          <ToolPre failed>{part.error}</ToolPre>
        </div>
      )}
    </Wrap>
  )
}

function FindOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const input = part.input ?? {}
  const pattern = strv(input.pattern) || strv(input.query)
  const body = failed ? part.error || part.output || "" : part.output || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {pattern && <div className="text-n800 font-mono text-xs break-words">{pattern}</div>}
      {body && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.matches")}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{body}</ToolDetailText>
        </div>
      )}
    </Wrap>
  )
}

function AgentOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const input = part.input ?? {}
  const description = strv(input.description) || strv(input.skill) || strv(input.prompt)
  const body = failed ? part.error || part.output || "" : part.output || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {description && <div className="break-words">{description}</div>}
      {body && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.result")}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{body}</ToolDetailText>
        </div>
      )}
    </Wrap>
  )
}

/** A skill load: just which skill, and whether it loaded.
 *
 *  The output is the skill's full instruction document — thousands of words
 *  written for the model, not the reader. Showing it turned every skill call
 *  into a wall of manual the user had to scroll past to find the answer. */
function SkillOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const name = strv((part.input ?? {}).skill) || part.title || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {name && <div className="font-mono text-xs break-words">{name}</div>}
      {failed && part.error && (
        <div>
          <ToolMiniLabel>{t("toolDetail.error")}</ToolMiniLabel>
          <ToolDetailText failed>{part.error}</ToolDetailText>
        </div>
      )}
    </Wrap>
  )
}

function GenericOutput({ part, failed }: LayoutProps) {
  const { t } = useTranslation("chat")
  const input = part.input ?? {}
  const args = Object.keys(input).length > 0 ? safeStringify(input) : ""
  const body = failed ? part.error || part.output || "" : part.output || ""
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {args && (
        <div>
          <ToolMiniLabel>{t("toolDetail.arguments")}</ToolMiniLabel>
          <ToolPre>{args}</ToolPre>
        </div>
      )}
      {body && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.result")}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{body}</ToolDetailText>
        </div>
      )}
    </Wrap>
  )
}

function SubtaskOutput({ part }: { part: SubtaskPart }) {
  const { t } = useTranslation("chat")
  const failed = part.status === "error"
  return (
    <Wrap failed={failed}>
      <StatusLine status={part.status} />
      {part.description && <div className="break-words">{part.description}</div>}
      {part.output && (
        <div>
          <ToolMiniLabel>{failed ? t("toolDetail.error") : t("toolDetail.result")}</ToolMiniLabel>
          <ToolDetailText failed={failed}>{part.output}</ToolDetailText>
        </div>
      )}
    </Wrap>
  )
}

/** Render a tool/subtask call's detail column with its layout-specific shape. */
export function ToolOutput({ part }: { part: ToolPart | SubtaskPart }) {
  if (part.type === "subtask") return <SubtaskOutput part={part} />
  const failed = part.status === "error" || Boolean(part.error?.trim())
  switch (resolveToolLayout(part.tool)) {
    case "search":
      return <SearchOutput part={part} failed={failed} />
    case "fetch":
      return <FetchOutput part={part} failed={failed} />
    case "shell":
      return <ShellOutput part={part} failed={failed} />
    case "file":
      return <FileOutput part={part} failed={failed} />
    case "find":
      return <FindOutput part={part} failed={failed} />
    case "skill":
      return <SkillOutput part={part} failed={failed} />
    case "agent":
      return <AgentOutput part={part} failed={failed} />
    default:
      return <GenericOutput part={part} failed={failed} />
  }
}
