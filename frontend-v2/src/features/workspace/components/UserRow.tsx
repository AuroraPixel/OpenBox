import { useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { MoreHorizontal } from "lucide-react"
import { useAuthStore } from "@/shared/api/auth-store"
import { http } from "@/shared/api/http"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import { paths } from "@/shared/router/paths"

export function UserRow({ sessionCount }: { sessionCount: number }) {
  const { t } = useTranslation("workspace")
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [menuOpen, setMenuOpen] = useState(false)

  const signOut = async () => {
    setMenuOpen(false)
    await http.post("/api/auth/logout").catch(() => undefined)
    useAuthStore.getState().clearAuth()
    navigate(paths.landing)
  }

  return (
    <div className="relative mt-1 flex-none">
      <Menu open={menuOpen} onClose={() => setMenuOpen(false)} className="start-1 end-1 bottom-11.5 z-25">
        <MenuItem
          onClick={() => {
            setMenuOpen(false)
            navigate(paths.settings())
          }}
        >
          {t("settings")}
        </MenuItem>
        <MenuItem onClick={() => void signOut()}>{t("common:action.signOut", { ns: "common" })}</MenuItem>
      </Menu>
      <div className="flex items-center gap-2.5 rounded-full px-2.5 py-2 hover:bg-n200">
        <span
          className="flex size-7 flex-none items-center justify-center rounded-full bg-n800 text-sm font-semibold text-bg uppercase"
          aria-hidden
        >
          {(user?.username ?? "?").slice(0, 1)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col leading-snug">
          <span className="truncate text-md font-medium">{user?.username}</span>
          <span className="truncate text-xs text-n600">
            {t("userLine", { role: user?.role ?? "user", count: sessionCount })}
          </span>
        </span>
        <button
          type="button"
          title={t("common:action.more", { ns: "common" })}
          aria-label={t("common:action.more", { ns: "common" })}
          className="flex size-6 flex-none items-center justify-center rounded-full text-n600"
          onClick={() => setMenuOpen((v) => !v)}
        >
          <MoreHorizontal size={15} strokeWidth={2.4} />
        </button>
      </div>
    </div>
  )
}
