import { useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { ChevronRight, MoreHorizontal, Plus } from "lucide-react"
import type { Project } from "@/shared/types/api"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import { cn } from "@/shared/lib/cn"
import { paths } from "@/shared/router/paths"
import { useRenameProject } from "../api/projects"
import { useWorkspaceUi } from "../stores/ui"

interface ProjectRowProps {
  project: Project | null // null = the "unsorted" pseudo group
  forceExpanded: boolean
  onAskDelete: () => void
  children: ReactNode
}

export function ProjectRow({ project, forceExpanded, onAskDelete, children }: ProjectRowProps) {
  const { t } = useTranslation("workspace")
  const navigate = useNavigate()
  const rename = useRenameProject()
  const groupId = project?.id ?? "__unsorted"
  const expanded = useWorkspaceUi((s) => s.expanded[groupId] ?? true) || forceExpanded
  const toggleProject = useWorkspaceUi((s) => s.toggleProject)
  const selected = useWorkspaceUi((s) => s.selectedProject === (project?.id ?? null) && !!project)
  const selectProject = useWorkspaceUi((s) => s.selectProject)

  // Touching a project makes it the current one — the top "new chat" button
  // creates its session here.
  const touch = () => selectProject(project?.id ?? null)

  const [hover, setHover] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameValue, setRenameValue] = useState("")

  const name = project?.name ?? t("unsorted")

  const commitRename = () => {
    const value = renameValue.trim()
    if (project && value && value !== project.name) rename.mutate({ id: project.id, name: value })
    setRenaming(false)
  }

  return (
    <div className="flex flex-col">
      <div
        className={cn(
          "relative flex min-h-8 items-center gap-2 rounded-full py-1.5 ps-2.5 pe-2",
          hover && "bg-hairsoft",
        )}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        <button
          type="button"
          className={cn("flex flex-none text-n600 transition-transform", expanded && "rotate-90")}
          onClick={() => {
            toggleProject(groupId)
            touch()
          }}
          aria-label={name}
          aria-expanded={expanded}
        >
          <ChevronRight size={12} strokeWidth={2.75} />
        </button>
        {renaming && project ? (
          <input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename()
              if (e.key === "Escape") setRenaming(false)
            }}
            onBlur={commitRename}
            className="min-w-0 flex-1 border-none bg-transparent text-md font-semibold text-ink outline-none"
            // eslint-disable-next-line jsx-a11y/no-autofocus
            autoFocus
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              toggleProject(groupId)
              touch()
            }}
            className="flex min-w-0 flex-1 items-center gap-1.5 truncate text-start text-md font-medium"
          >
            <span className="truncate">{name}</span>
            {selected && <span className="size-1.5 flex-none rounded-full bg-accent" aria-hidden />}
          </button>
        )}
        {hover && !renaming && (
          <span className="flex flex-none gap-0.5 text-n700">
            <button
              type="button"
              title={t("newChatIn")}
              aria-label={t("newChatIn")}
              className="flex size-5.5 items-center justify-center rounded-full hover:bg-n200"
              onClick={() => {
                touch()
                navigate(project ? `${paths.app}?project=${project.id}` : paths.app)
              }}
            >
              <Plus size={14} strokeWidth={2.75} />
            </button>
            {project && (
              <button
                type="button"
                title={t("common:action.more", { ns: "common" })}
                aria-label={t("common:action.more", { ns: "common" })}
                className="flex size-5.5 items-center justify-center rounded-full hover:bg-n200"
                onClick={() => setMenuOpen((v) => !v)}
              >
                <MoreHorizontal size={15} strokeWidth={2.4} />
              </button>
            )}
          </span>
        )}
        <Menu open={menuOpen} onClose={() => setMenuOpen(false)} className="end-1 top-8 w-43">
          <MenuItem
            onClick={() => {
              setMenuOpen(false)
              setRenaming(true)
              setRenameValue(project?.name ?? "")
            }}
          >
            {t("rename")}
          </MenuItem>
          <MenuItem
            onClick={() => {
              setMenuOpen(false)
              touch()
              navigate(project ? `${paths.app}?project=${project.id}` : paths.app)
            }}
          >
            {t("newChatIn")}
          </MenuItem>
          <MenuItem
            danger
            onClick={() => {
              setMenuOpen(false)
              onAskDelete()
            }}
          >
            {t("deleteProject")}
          </MenuItem>
        </Menu>
      </div>
      {expanded && <div className="flex flex-col gap-px pb-2">{children}</div>}
    </div>
  )
}
