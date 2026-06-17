export interface PermissionRequest {
  id: string
  session_id: string
  tool: string
  input: Record<string, unknown>
  patterns?: string[]
  always?: string[] // Broader patterns stored when user clicks "always allow"
  metadata?: Record<string, unknown>
  is_doom_loop?: boolean
  created_at: string
}

export type PermissionAction = "once" | "always" | "reject"

export interface PermissionReplied {
  id: string
  session_id: string
  action: PermissionAction
}
