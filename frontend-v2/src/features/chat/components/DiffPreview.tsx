// One changed file, as a quiet list row: path plus how much moved. The diff
// itself belongs in the review panel — dumping hundreds of lines into the
// conversation buries the answer the user actually came for.
import { useTranslation } from "react-i18next"
import { FileDiff } from "lucide-react"
import { emitAppEvent } from "@/shared/events/bus"
import type { PatchFile } from "@/shared/types/api"
import { usePrefetchSessionDiff } from "../api/diff"

interface Props {
  file: PatchFile
  sessionId: string
}

export function DiffPreview({ file, sessionId }: Props) {
  const { t } = useTranslation("chat")
  const prefetch = usePrefetchSessionDiff(sessionId)
  const name = file.path.split("/").pop() ?? file.path
  const dir = file.path.slice(0, file.path.length - name.length)

  return (
    <button
      type="button"
      onClick={() => emitAppEvent("workbench.open", { kind: "review", file: file.path })}
      onMouseEnter={prefetch}
      onFocus={prefetch}
      title={t("diff.openReview")}
      className="group/diff text-n600 hover:text-ink flex w-full max-w-165 items-center gap-2 py-0.5 text-start transition-colors"
    >
      <FileDiff className="size-3.5 flex-none opacity-70" />
      <span className="min-w-0 truncate font-mono text-xs">
        <span className="opacity-70">{dir}</span>
        {name}
      </span>
      {file.additions > 0 && <span className="text-s700 flex-none font-mono text-xs">+{file.additions}</span>}
      {file.deletions > 0 && <span className="text-danger flex-none font-mono text-xs">−{file.deletions}</span>}
      <span className="text-n500 group-hover/diff:text-a700 flex-none text-xs transition-colors">
        {t("reviewGo")}
      </span>
    </button>
  )
}
