// Query key factory for the chat feature. Every key carries the user id so
// switching accounts can never serve another user's cache (§7.2).
export const chatKeys = {
  messages: (userId: string, sessionId: string) => ["messages", userId, sessionId] as const,
  todo: (userId: string, sessionId: string) => ["todo", userId, sessionId] as const,
  config: (userId: string) => ["config", userId] as const,
  permissions: (userId: string) => ["permissions", userId] as const,
  questions: (userId: string) => ["questions", userId] as const,
}
