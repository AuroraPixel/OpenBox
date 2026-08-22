// Public surface of the chat feature — only what the workspace routes consume.
export { ChatFlow } from "./components/ChatFlow"
export { Composer } from "./components/Composer"
export { EmptyState } from "./components/EmptyState"
export { PermissionCard } from "./components/PermissionCard"
export { QuestionDock } from "./components/QuestionDock"

export { useChatEvents } from "./hooks/useChatEvents"
export { useSendChat } from "./hooks/useSendChat"
export { useStartChat } from "./hooks/useStartChat"

export { useMessagesQuery, useAbortSession } from "./api/messages"
export { useAddTodoItem, useRemoveTodoItem, useTodoQuery } from "./api/todo"
export { useChatAgents, type ChatAgent } from "./api/agents"
export { usePermissionsQuery } from "./api/permission"
export { useQuestionsQuery } from "./api/question"

export { useStreamStore, isBusyStatus } from "./stores/stream"
export { usePendingStore } from "./stores/pending"

export { mergeTurns } from "./lib/turn-view"
