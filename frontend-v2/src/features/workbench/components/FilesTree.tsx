// The Files tree column: a filter box, a cwd breadcrumb, and a single-level
// listing (directories first with a chevron, then files with a badge). Dirs
// navigate; files open in the viewer. A left-edge handle resizes the column.
// The parent remounts this via `key` to reset cwd when the sandbox or the opened
// file's folder changes — so no derived-state effects are needed.
import type { MouseEvent as ReactMouseEvent } from "react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronRight } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { fileBadge, toneBg, toneFg } from "@/features/workbench/utils/glyphs"
import { useFileListQuery } from "@/features/workbench/api/files"
import type { FileNode } from "@/features/workbench/api/files"

interface FilesTreeProps {
  containerId: string | null
  /** Top of the browsable tree (the project directory) — crumbs never go above it. */
  root: string
  initialCwd: string
  openFile: string | null
  onOpenFile: (path: string) => void
  width: number
  narrow: boolean
  onStartDrag: (e: ReactMouseEvent) => void
}

function sortNodes(nodes: FileNode[]): FileNode[] {
  return [...nodes].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

export function FilesTree(props: FilesTreeProps) {
  const { containerId, root, initialCwd, openFile, onOpenFile, width, narrow, onStartDrag } = props
  const { t } = useTranslation("workbench")
  const [cwd, setCwd] = useState(initialCwd)
  const [filter, setFilter] = useState("")
  const { data } = useFileListQuery(containerId, cwd)

  const nodes = sortNodes(data ?? []).filter((n) =>
    filter ? n.name.toLowerCase().includes(filter.toLowerCase()) : true,
  )
  // Crumbs start at the project root, not "/": the first crumb is the root
  // directory itself, then only the segments inside it — browsing never climbs
  // above the project. A cwd outside the root (a file opened from
  // /workspace/uploads, say) falls back to its own full path so that one
  // location stays navigable.
  const inRoot = cwd === root || cwd.startsWith(`${root}/`)
  const base = inRoot ? root : ""
  const rel = inRoot ? cwd.slice(root.length) : cwd
  const segments = [
    ...(inRoot ? [{ label: root.split("/").pop() || root, target: root }] : []),
    ...rel
      .split("/")
      .filter(Boolean)
      .map((seg, i, all) => ({ label: seg, target: `${base}/${all.slice(0, i + 1).join("/")}` })),
  ]

  return (
    <div
      className={cn(
        "relative flex min-h-0 flex-col rounded-2xl border border-hair bg-card",
        narrow ? "flex-1" : "flex-none",
      )}
      style={narrow ? undefined : { width }}
    >
      {!narrow && (
        <div
          onMouseDown={onStartDrag}
          className="absolute top-0 bottom-0 -left-1.5 z-10 w-2 cursor-col-resize"
        />
      )}
      <div className="flex-none p-2.5 pb-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("files.filter")}
          className="h-7.5 w-full rounded-full border border-hair bg-transparent px-3 text-xs outline-none"
        />
      </div>
      <div className="flex flex-none flex-wrap items-center gap-0.5 px-3 pb-1.5 text-xs text-n600">
        {segments.map((seg, i) => (
          <span key={seg.target} className="flex items-center gap-0.5">
            {i > 0 && <ChevronRight size={11} strokeWidth={2.4} className="text-n500" />}
            <button type="button" onClick={() => setCwd(seg.target)} className="hover:text-n800">
              {seg.label}
            </button>
          </span>
        ))}
      </div>
      <div className="scr flex min-h-0 flex-1 flex-col gap-px overflow-auto px-2 pb-2.5">
        {nodes.map((n) => {
          const path = `${cwd}/${n.name}`
          const badge = n.is_dir ? null : fileBadge(n.name)
          const selected = !n.is_dir && openFile === path
          return (
            <button
              key={n.name}
              type="button"
              onClick={() => (n.is_dir ? setCwd(path) : onOpenFile(path))}
              className={cn(
                "flex min-h-7 items-center gap-2 rounded-full px-2.5 text-start",
                selected ? "bg-n200" : "hover:bg-hairsoft",
              )}
            >
              {n.is_dir ? (
                <ChevronRight size={12} strokeWidth={2.6} className="flex-none text-n500" />
              ) : (
                badge && (
                  <span className={cn("flex h-4.5 w-5.5 flex-none items-center justify-center rounded-sm font-mono text-2xs font-semibold", toneBg(badge.tone), toneFg(badge.tone))}>
                    {badge.text}
                  </span>
                )
              )}
              <span className={cn("min-w-0 flex-1 truncate text-xs", selected ? "font-medium" : "text-n800")}>
                {n.name}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
