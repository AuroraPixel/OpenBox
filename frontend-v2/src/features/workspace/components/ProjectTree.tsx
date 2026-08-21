import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useParams } from "react-router"
import type { Project, Session } from "@/shared/types/api"
import { Dialog, DialogActions, DialogBody, DialogTitle } from "@/shared/ui/Dialog"
import { paths } from "@/shared/router/paths"
import { useDeleteProject } from "../api/projects"
import { useDeleteSession } from "../api/sessions"
import { useWorkspaceUi } from "../stores/ui"
import { ProjectRow } from "./ProjectRow"
import { SessionRow } from "./SessionRow"

interface ProjectTreeProps {
  projects: Project[]
  sessions: Session[]
  searching: boolean
}

interface Group {
  project: Project | null
  sessions: Session[]
}

export function ProjectTree({ projects, sessions, searching }: ProjectTreeProps) {
  const { t } = useTranslation("workspace")
  const navigate = useNavigate()
  const { sessionId: activeSessionId } = useParams()
  const deleteProject = useDeleteProject()
  const deleteSession = useDeleteSession()
  const [confirmProject, setConfirmProject] = useState<Project | null>(null)
  const [confirmSession, setConfirmSession] = useState<Session | null>(null)

  const groups = useMemo<Group[]>(() => {
    const byProject = new Map<string, Session[]>()
    const loose: Session[] = []
    for (const s of sessions) {
      if (s.project_id) {
        const list = byProject.get(s.project_id) ?? []
        list.push(s)
        byProject.set(s.project_id, list)
      } else {
        loose.push(s)
      }
    }
    const result: Group[] = projects.map((p) => ({ project: p, sessions: byProject.get(p.id) ?? [] }))
    if (loose.length > 0) result.push({ project: null, sessions: loose })
    return result
  }, [projects, sessions])

  const onDeleteProject = () => {
    if (!confirmProject) return
    deleteProject.mutate(confirmProject.id)
    const ui = useWorkspaceUi.getState()
    if (ui.selectedProject === confirmProject.id) ui.selectProject(null)
    if (groups.some((g) => g.project?.id === confirmProject.id && g.sessions.some((s) => s.id === activeSessionId))) {
      navigate(paths.app)
    }
    setConfirmProject(null)
  }

  const onDeleteSession = () => {
    if (!confirmSession) return
    deleteSession.mutate(confirmSession.id)
    if (confirmSession.id === activeSessionId) navigate(paths.app)
    setConfirmSession(null)
  }

  return (
    <>
      {groups.map((g) => (
        <div key={g.project?.id ?? "unsorted"} className="flex flex-col">
          <ProjectRow
            project={g.project}
            forceExpanded={searching}
            onAskDelete={() => g.project && setConfirmProject(g.project)}
          >
            {g.sessions.map((s) => (
              <SessionRow
                key={s.id}
                session={s}
                active={s.id === activeSessionId}
                onAskDelete={() => setConfirmSession(s)}
              />
            ))}
            {g.sessions.length === 0 && (
              <div className="ps-7.5 pe-3 py-1 text-md text-n600">{t("noChats")}</div>
            )}
          </ProjectRow>
        </div>
      ))}

      <Dialog open={confirmProject !== null} onClose={() => setConfirmProject(null)}>
        <DialogTitle>{t("delTitle", { name: confirmProject?.name ?? "" })}</DialogTitle>
        <DialogBody>{t("delBody")}</DialogBody>
        <DialogActions>
          <button
            type="button"
            className="text-base text-n700"
            onClick={() => setConfirmProject(null)}
          >
            {t("common:action.cancel", { ns: "common" })}
          </button>
          <button
            type="button"
            className="rounded-full bg-danger px-4.5 py-2 text-base text-bg"
            onClick={onDeleteProject}
          >
            {t("common:action.delete", { ns: "common" })}
          </button>
        </DialogActions>
      </Dialog>

      <Dialog open={confirmSession !== null} onClose={() => setConfirmSession(null)}>
        <DialogTitle>{t("delChatTitle")}</DialogTitle>
        <DialogBody>{t("delChatBody")}</DialogBody>
        <DialogActions>
          <button type="button" className="text-base text-n700" onClick={() => setConfirmSession(null)}>
            {t("common:action.cancel", { ns: "common" })}
          </button>
          <button
            type="button"
            className="rounded-full bg-danger px-4.5 py-2 text-base text-bg"
            onClick={onDeleteSession}
          >
            {t("common:action.delete", { ns: "common" })}
          </button>
        </DialogActions>
      </Dialog>
    </>
  )
}
