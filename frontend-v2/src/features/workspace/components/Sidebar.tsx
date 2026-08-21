import { useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { FolderPlus, PanelLeft, Plus, Search } from "lucide-react"
import { BrandMark } from "@/shared/ui/BrandMark"
import { paths } from "@/shared/router/paths"
import { useProjectsQuery, useCreateProject } from "../api/projects"
import { useSessionsQuery } from "../api/sessions"
import { useWorkspaceUi } from "../stores/ui"
import { ProjectTree } from "./ProjectTree"
import { UserRow } from "./UserRow"

export function Sidebar() {
  const { t } = useTranslation("workspace")
  const navigate = useNavigate()
  const width = useWorkspaceUi((s) => s.sidebarWidth)
  const collapsed = useWorkspaceUi((s) => s.sidebarCollapsed)
  const toggleSidebar = useWorkspaceUi((s) => s.toggleSidebar)
  const setSidebarWidth = useWorkspaceUi((s) => s.setSidebarWidth)

  const projects = useProjectsQuery()
  const sessions = useSessionsQuery()
  const createProject = useCreateProject()
  const selectedProject = useWorkspaceUi((s) => s.selectedProject)
  // A stale selection (deleted project) must not silently file new chats
  // into a project that no longer exists.
  const newChatProject =
    selectedProject && (projects.data ?? []).some((p) => p.id === selectedProject)
      ? selectedProject
      : null

  const [draftOpen, setDraftOpen] = useState(false)
  const [draftName, setDraftName] = useState("")
  const [query, setQuery] = useState("")
  const dragStart = useRef<{ x: number; w: number } | null>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = sessions.data ?? []
    if (!q) return all
    return all.filter((s) => s.title.toLowerCase().includes(q))
  }, [sessions.data, query])

  const commitDraft = () => {
    const name = draftName.trim()
    setDraftOpen(false)
    setDraftName("")
    if (name) createProject.mutate(name)
  }

  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault()
    dragStart.current = { x: e.clientX, w: width }
    const move = (ev: MouseEvent) => {
      if (dragStart.current) setSidebarWidth(dragStart.current.w + ev.clientX - dragStart.current.x)
    }
    const up = () => {
      dragStart.current = null
      window.removeEventListener("mousemove", move)
      window.removeEventListener("mouseup", up)
      document.body.style.userSelect = ""
    }
    window.addEventListener("mousemove", move)
    window.addEventListener("mouseup", up)
    document.body.style.userSelect = "none"
  }

  if (collapsed) return null

  return (
    <aside className="relative flex min-h-0 flex-none flex-col bg-rail" style={{ width }}>
      <div className="flex min-h-0 flex-1 flex-col ps-4.5 pe-3 pt-3.5 pb-2.5">
        <div className="flex items-center gap-2.5 pt-0.5 pb-4">
          <BrandMark className="min-w-0 flex-1" />
          <button
            type="button"
            className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
            onClick={() => setDraftOpen(true)}
            title={t("newProject")}
            aria-label={t("newProject")}
          >
            <FolderPlus size={17} strokeWidth={2.4} />
          </button>
          <button
            type="button"
            className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-hairsoft"
            onClick={toggleSidebar}
            title={t("collapse")}
            aria-label={t("collapse")}
          >
            <PanelLeft size={17} strokeWidth={2.4} />
          </button>
        </div>

        <button
          type="button"
          // Keep the current project: the new chat is created inside it, and
          // the tree's selection/expansion stays exactly as it was.
          onClick={() => navigate(newChatProject ? `${paths.app}?project=${newChatProject}` : paths.app)}
          className="flex h-10 flex-none items-center justify-center gap-2 rounded-full bg-a200 text-base font-medium text-ink hover:bg-a300"
        >
          <Plus size={16} strokeWidth={2.75} />
          {t("newChat")}
        </button>

        <div className="relative my-3 flex-none">
          <Search size={15} strokeWidth={2.4} className="absolute start-3.5 top-2.5 text-n500" aria-hidden />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("search")}
            className="h-8.5 w-full rounded-full border border-hair bg-transparent ps-9 pe-3 text-md text-ink outline-none placeholder:text-n500 focus-visible:border-n400"
          />
        </div>

        {draftOpen && (
          <div className="mb-1 flex flex-none items-center gap-2 rounded-full border border-hair px-3.5 py-2">
            <span className="size-1.75 rounded-full bg-accent" aria-hidden />
            <input
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitDraft()
                if (e.key === "Escape") setDraftOpen(false)
              }}
              onBlur={commitDraft}
              placeholder={t("projectName")}
              className="min-w-0 flex-1 border-none bg-transparent text-base text-ink outline-none"
              // eslint-disable-next-line jsx-a11y/no-autofocus
              autoFocus
            />
          </div>
        )}

        <div className="scr -mx-1 flex min-h-0 flex-1 flex-col gap-0.5 overflow-x-hidden overflow-y-auto p-1">
          <ProjectTree projects={projects.data ?? []} sessions={filtered} searching={query.trim().length > 0} />
        </div>

        <UserRow sessionCount={(sessions.data ?? []).length} />
      </div>
      <button
        type="button"
        aria-hidden
        tabIndex={-1}
        onMouseDown={startDrag}
        className="absolute top-0 bottom-0 -end-1 z-6 w-2 cursor-col-resize"
      />
    </aside>
  )
}
