import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { ApiError } from "@/shared/api/http"
import { useApiErrorMessage } from "@/shared/hooks/useApiErrorMessage"

/**
 * Maps auth failures to friendly copy. The backend returns a `detail` string
 * (no machine code), so login 401 → "wrong credentials" and register 409 →
 * "user exists" are recognised by status before falling back to the generic map.
 */
export function useAuthErrorMessage() {
  const generic = useApiErrorMessage()
  const { t } = useTranslation("errors")
  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        if (err.status === 401) return t("AUTH_INVALID_CREDENTIALS")
        if (err.status === 409) return t("AUTH_USER_EXISTS")
      }
      return generic(err)
    },
    [generic, t],
  )
}
