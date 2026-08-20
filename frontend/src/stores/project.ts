import { create } from "zustand"
import { api } from "@/services/api"
import type { Project } from "@/types"

/**
 * Which project the UI is scoped to.
 *
 * `null` means "All projects" — the sidebar shows every session, and a new chat
 * lands in the default project. Persisted so reopening the app returns you to
 * the project you were working in, the way a terminal reopens in its directory.
 */
const STORAGE_KEY = "openbox.currentProjectId"

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* private mode, quota — scoping just won't survive a reload */
  }
}

interface ProjectStore {
  projects: Project[]
  currentProjectId: string | null
  loading: boolean
  error: string | null

  loadProjects: () => Promise<Project[]>
  setCurrentProject: (id: string | null) => void
  createProject: (data: { name: string; slug?: string; description?: string }) => Promise<Project>
  renameProject: (id: string, name: string) => Promise<void>
  deleteProject: (id: string) => Promise<void>
  reset: () => void

  currentProject: () => Project | null
}

export const useProjectStore = create<ProjectStore>((set, get) => ({
  projects: [],
  currentProjectId: readStored(),
  loading: false,
  error: null,

  loadProjects: async () => {
    set({ loading: true, error: null })
    try {
      const projects = await api.listProjects()
      // A stored id whose project has been deleted would silently filter the
      // sidebar down to nothing, so fall back to All projects.
      const current = get().currentProjectId
      const stillExists = current ? projects.some((p) => p.id === current) : true
      set({
        projects,
        loading: false,
        currentProjectId: stillExists ? current : null,
      })
      if (!stillExists) writeStored(null)
      return projects
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "Failed to load projects" })
      return []
    }
  },

  setCurrentProject: (id) => {
    writeStored(id)
    set({ currentProjectId: id })
  },

  createProject: async (data) => {
    const project = await api.createProject(data)
    set((s) => ({ projects: [...s.projects, project] }))
    return project
  },

  renameProject: async (id, name) => {
    const updated = await api.renameProject(id, name)
    set((s) => ({ projects: s.projects.map((p) => (p.id === id ? { ...p, ...updated } : p)) }))
  },

  deleteProject: async (id) => {
    await api.deleteProject(id)
    set((s) => ({
      projects: s.projects.filter((p) => p.id !== id),
      currentProjectId: s.currentProjectId === id ? null : s.currentProjectId,
    }))
    if (get().currentProjectId === null) writeStored(null)
  },

  reset: () => {
    writeStored(null)
    set({ projects: [], currentProjectId: null, loading: false, error: null })
  },

  currentProject: () => {
    const { projects, currentProjectId } = get()
    return projects.find((p) => p.id === currentProjectId) ?? null
  },
}))
