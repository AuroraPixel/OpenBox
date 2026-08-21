// Files tab: a header (sandbox › file · copy · list toggle), the content viewer,
// and the resizable tree column. In a narrow panel the tree replaces the viewer.
import type { MouseEvent as ReactMouseEvent } from "react"
import { useTranslation } from "react-i18next"
import { Copy, List } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { useCopy } from "@/shared/hooks/useCopy"
import { toast } from "@/shared/ui/Toast"
import { usePanelStore } from "@/features/workbench/stores/panel"
import { splitPath } from "@/features/workbench/utils/glyphs"
import { useRunningContainer } from "@/features/workbench/api/containers"
import { useSessionWorkdir } from "@/features/workbench/api/workdir"
import { EmptyState } from "./EmptyState"
import { FileViewer } from "./FileViewer"
import { FilesTree } from "./FilesTree"

function resolvePath(openFile: string | null, root: string): string | null {
  if (!openFile) return null
  return openFile.startsWith("/") ? openFile : `${root}/${openFile.replace(/^\/+/, "")}`
}

function dirOf(path: string, root: string): string {
  const cut = path.lastIndexOf("/")
  return cut > 0 ? path.slice(0, cut) : root
}

interface FilesTabProps {
  narrow: boolean
  sessionId: string | null
}

export function FilesTab({ narrow, sessionId }: FilesTabProps) {
  const { t } = useTranslation("workbench")
  const running = useRunningContainer()
  const containerId = running?.id ?? null
  // Scope the tree to the session's project directory — /workspace is the
  // agent's whole activity space, not the project being worked on.
  const workdir = useSessionWorkdir(sessionId)
  const openFile = usePanelStore((s) => s.openFile)
  const setOpenFile = usePanelStore((s) => s.setOpenFile)
  const treeOpen = usePanelStore((s) => s.treeOpen)
  const treeWidth = usePanelStore((s) => s.treeWidth)
  const toggleTree = usePanelStore((s) => s.toggleTree)
  const setTreeWidth = usePanelStore((s) => s.setTreeWidth)
  const { copy } = useCopy()

  if (!containerId) {
    return <EmptyState title={t("sandbox.none")} hint={t("terminal.emptyHint")} />
  }
  if (sessionId && !workdir) {
    // One round-trip while the session detail loads; rooting at /workspace in
    // the meantime would flash the whole sandbox before snapping to the project.
    return <EmptyState title={t("files.pickFile")} />
  }

  const root = workdir ?? "/workspace"
  const fullPath = resolvePath(openFile, root)
  const initialCwd = fullPath ? dirOf(fullPath, root) : root
  const rootName = splitPath(root).base || root

  const showTree = treeOpen
  const showViewer = !(narrow && treeOpen)
  const name = fullPath ? splitPath(fullPath).base : ""

  const startTreeDrag = (e: ReactMouseEvent) => {
    e.preventDefault()
    const x0 = e.clientX
    const w0 = usePanelStore.getState().treeWidth
    const move = (ev: MouseEvent) => setTreeWidth(w0 - (ev.clientX - x0))
    const up = () => {
      window.removeEventListener("mousemove", move)
      window.removeEventListener("mouseup", up)
      document.body.style.userSelect = ""
    }
    window.addEventListener("mousemove", move)
    window.addEventListener("mouseup", up)
    document.body.style.userSelect = "none"
  }

  const onCopy = () => {
    if (!fullPath) return
    copy(fullPath)
    toast("info", t("files.pathCopied"))
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-none items-center gap-2 px-3 pb-2.5">
        {!narrow && <span className="flex-none text-sm text-n600">{`${rootName} ›`}</span>}
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{name || t("files.pickFile")}</span>
        <button
          type="button"
          onClick={onCopy}
          disabled={!fullPath}
          title={t("files.copyPath")}
          aria-label={t("files.copyPath")}
          className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft disabled:opacity-40"
        >
          <Copy size={14} strokeWidth={2.2} />
        </button>
        <button
          type="button"
          onClick={toggleTree}
          title={t("files.fileList")}
          aria-label={t("files.fileList")}
          className={cn(
            "flex size-7.5 flex-none items-center justify-center rounded-full hover:bg-n200",
            treeOpen ? "text-a700" : "text-n700",
          )}
        >
          <List size={15} strokeWidth={2.4} />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 gap-2.5 px-3 pb-3">
        {showViewer && (
          <div className="scr min-w-0 flex-1 overflow-auto rounded-2xl border border-hair bg-card p-4">
            <FileViewer containerId={containerId} path={fullPath} />
          </div>
        )}
        {showTree && (
          <FilesTree
            key={`${containerId}:${initialCwd}`}
            containerId={containerId}
            root={root}
            initialCwd={initialCwd}
            openFile={fullPath}
            onOpenFile={setOpenFile}
            width={treeWidth}
            narrow={narrow}
            onStartDrag={startTreeDrag}
          />
        )}
      </div>
    </div>
  )
}
