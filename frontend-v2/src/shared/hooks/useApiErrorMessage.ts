import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import { ApiError } from "@/shared/api/http"

/** Maps a thrown error to user copy via the errors namespace (§10.7). */
export function useApiErrorMessage() {
  const { t } = useTranslation("errors")
  return useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError) {
        const byCode = t(err.code, { defaultValue: "" })
        if (byCode) return byCode
        const byStatus = t(`HTTP_${err.status}`, { defaultValue: "" })
        if (byStatus) return byStatus
        return t("fallback")
      }
      if (err instanceof TypeError) return t("network")
      return t("fallback")
    },
    [t],
  )
}
