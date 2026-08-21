// WS event contract — single source of truth for event names and payloads
// the backend publishes over /ws/agent (backend bus, see api/ws.py).
import type {
  MessagePart,
  MessageWithParts,
  PermissionRequest,
  QuestionRequest,
  SessionStatus,
  TokenUsage,
} from "@/shared/types/api"

export interface WsEventMap {
  // connection lifecycle (client-side synthetic)
  "__connected": Record<string, never>
  "__disconnected": Record<string, never>

  "session.status": { sessionId: string; status: SessionStatus }
  "session.finalizing": { sessionId: string }
  "session.error": { sessionId: string; error?: { message?: string; code?: string } }
  "session.title": { sessionId: string; title: string }
  "session.updated": {
    sessionId: string
    token_usage?: TokenUsage
    agent?: string
    planUpdated?: boolean
  }
  "session.diff": { sessionId: string }
  "session.compaction.start": { sessionId: string }
  "session.compaction.complete": { sessionId: string; summary?: string }
  toast: { userId: string; level: "info" | "error" | "warning"; message: string }

  "message.created": { sessionId: string; message: MessageWithParts }
  "message.updated": { sessionId: string; message: MessageWithParts }
  "message.text_delta": { sessionId: string; messageId: string; partId: string; text: string }

  "part.created": { sessionId: string; messageId: string; part: MessagePart }
  "part.updated": { sessionId: string; messageId: string; part: MessagePart }
  "part.delta": { sessionId: string; messageId: string; partId: string; delta: string }

  "tool.running": { sessionId: string; partId: string; data?: Record<string, unknown> }
  "tool.completed": { sessionId: string; partId: string; data?: Record<string, unknown> }
  "tool.error": { sessionId: string; partId: string; data?: Record<string, unknown> }

  "todo.updated": { sessionId: string }

  "permission.asked": PermissionRequest
  "permission.replied": { request_id: string; action?: string }
  "question.asked": QuestionRequest
  "question.replied": { request_id: string }
  "question.rejected": { request_id: string }
}

export type WsEventName = keyof WsEventMap
