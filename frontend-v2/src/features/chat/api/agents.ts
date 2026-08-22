// The agents a person may pick to talk to.
//
// Chat keeps its own reader rather than borrowing settings': the composer's
// mode picker is chat's own concern, and the feature boundary forbids
// reaching across. Both hit the same endpoint, which serves only agents that
// can hold a conversation — a subagent never appears here.
import { useQuery } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import { useUserId } from "./messages"

export interface ChatAgent {
  name: string
  description?: string
  model?: string
  /** "primary" | "subagent" | "all". Subagents are filtered out server-side. */
  mode?: string
  /** Accent colour the agent asked for, if any. */
  color?: string | null
}

export function useChatAgents() {
  const userId = useUserId()
  return useQuery({
    queryKey: ["chat-agents", userId],
    queryFn: () => http.get<ChatAgent[]>("/api/agent/agent"),
    staleTime: 60_000,
  })
}
