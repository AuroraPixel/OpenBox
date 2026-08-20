export interface Project {
  id: string
  name: string
  /** Directory name inside the sandbox. Fixed at creation; renaming changes only `name`. */
  slug: string
  description?: string | null
  /** Absolute path the agent works in, e.g. /workspace/my-app */
  directory: string
  created_at: string
  updated_at: string
  session_count: number
}
