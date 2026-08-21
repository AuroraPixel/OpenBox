// Query key factory — every key carries the user id so switching accounts
// can never serve another user's cache (ENGINEERING_SPEC §7.2).
export const workspaceKeys = {
  projects: (userId: string) => ["projects", userId] as const,
  sessions: (userId: string) => ["sessions", userId] as const,
  session: (userId: string, id: string) => ["session", userId, id] as const,
}
