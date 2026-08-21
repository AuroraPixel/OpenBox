// File content viewer: markdown files render as doc blocks (design docStyle),
// code renders with line numbers + the simple tokenizer, and unsupported /
// binary / oversized / missing states get a centered notice.
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { ApiError } from "@/shared/api/http"
import { Spinner } from "@/shared/ui/Spinner"
import { isDocPath } from "@/features/workbench/utils/glyphs"
import { tokenize } from "@/features/workbench/utils/tokenize"
import { toDocBlocks } from "@/features/workbench/utils/markdown"
import { useFileContentQuery } from "@/features/workbench/api/files"

const DOC_CLASS: Record<string, string> = {
  h1: "text-2xl font-medium tracking-tight",
  p: "text-base leading-relaxed text-n800",
  code: "font-mono text-sm border border-hair rounded-lg px-3.5 py-2.5 text-n800 whitespace-pre-wrap",
}

function Notice({ text }: { text: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-n600">{text}</div>
  )
}

interface FileViewerProps {
  containerId: string | null
  path: string | null
}

export function FileViewer({ containerId, path }: FileViewerProps) {
  const { t } = useTranslation("workbench")
  const { data, isLoading, isError, error } = useFileContentQuery(containerId, path)

  if (!path) return <Notice text={t("files.pickFile")} />
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    )
  }
  if (isError) {
    const status = error instanceof ApiError ? error.status : 0
    return <Notice text={status === 404 || status === 501 ? t("files.notSupported") : t("files.loadFailed")} />
  }

  const content = data?.content ?? ""
  if (content.includes("\u0000")) return <Notice text={t("files.binary")} />

  if (isDocPath(path)) {
    const blocks = toDocBlocks(content)
    return (
      <div data-testid="file-viewer-content" className="flex max-w-2xl flex-col gap-3.5">
        {data?.truncated && <div className="text-xs text-n600">{t("files.tooLarge", { limit: content.split("\n").length })}</div>}
        {blocks.map((b, i) => (
          <div key={i} className={DOC_CLASS[b.kind]}>
            {b.text}
          </div>
        ))}
      </div>
    )
  }

  const lines = content.split("\n")
  return (
    <div data-testid="file-viewer-content" className="flex min-w-max flex-col">
      {data?.truncated && (
        <div className="pb-2 text-xs text-n600">{t("files.tooLarge", { limit: lines.length })}</div>
      )}
      {lines.map((line, i) => (
        <div key={i} className="flex gap-4 font-mono text-sm leading-loose">
          <span className="w-6 flex-none select-none text-end text-n500">{i + 1}</span>
          <span className="whitespace-pre">
            {tokenize(line).map((tk, j) => (
              <span key={j} className={cn(tk.className)}>
                {tk.text}
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  )
}
