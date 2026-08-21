// Send-key preference: "enter" (Enter sends, Shift+Enter newline) vs
// "mod_enter" (⌘/Ctrl+Enter sends, Enter newline). Persisted under the free
// `extra` bag of /api/auth/me/preferences so it survives across devices,
// merged in so we never clobber a sibling key (mode/fontSize/locale).
//
// The query key ["prefs", userId] is intentionally identical to the settings
// feature's key so both share one cache entry (feature boundaries forbid
// importing that feature's helpers directly).
import { useCallback } from "react"
import type { KeyboardEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { http } from "@/shared/api/http"
import { useAuthStore } from "@/shared/api/auth-store"
import type { UserPreferences } from "@/shared/types/api"

export type SendShortcut = "enter" | "mod_enter"

const prefsKey = (userId: string) => ["prefs", userId] as const

function read(extra: Record<string, unknown> | null | undefined): SendShortcut {
  return extra?.sendShortcut === "mod_enter" ? "mod_enter" : "enter"
}

/** Does this keydown mean "send" under the active shortcut? Callers still have
 *  to gate IME composition themselves (isComposing / keyCode 229). */
export function matchesSend(shortcut: SendShortcut, e: KeyboardEvent<HTMLTextAreaElement>): boolean {
  if (e.key !== "Enter" || e.shiftKey) return false
  if (shortcut === "mod_enter") return e.metaKey || e.ctrlKey
  return true
}

export function useSendShortcut() {
  const userId = useAuthStore((s) => s.user?.id ?? "anonymous")
  const qc = useQueryClient()

  const { data: prefs } = useQuery({
    queryKey: prefsKey(userId),
    queryFn: () => http.get<UserPreferences>("/api/auth/me/preferences"),
  })
  const shortcut = read(prefs?.extra)

  const mutation = useMutation({
    mutationFn: (next: SendShortcut) =>
      http.put<UserPreferences>("/api/auth/me/preferences", {
        extra: { ...(prefs?.extra ?? {}), sendShortcut: next },
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: prefsKey(userId) }),
  })

  const setShortcut = useCallback((next: SendShortcut) => mutation.mutate(next), [mutation])
  const matches = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => matchesSend(shortcut, e),
    [shortcut],
  )

  return { shortcut, setShortcut, matches }
}
