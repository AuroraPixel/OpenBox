import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Check, CornerDownLeft } from "lucide-react"
import { Menu, MenuItem } from "@/shared/ui/Menu"
import type { SendShortcut } from "../../hooks/useSendShortcut"

interface Props {
  shortcut: SendShortcut
  onChange: (next: SendShortcut) => void
}

/** Toggles Enter vs ⌘/Ctrl+Enter as the send key. */
export function ShortcutPicker({ shortcut, onChange }: Props) {
  const { t } = useTranslation("chat")
  const [open, setOpen] = useState(false)
  const pick = (next: SendShortcut) => {
    onChange(next)
    setOpen(false)
  }
  return (
    <div className="relative flex-none">
      <Menu open={open} onClose={() => setOpen(false)} className="end-0 bottom-10 w-52">
        <MenuItem onClick={() => pick("enter")}>
          <span className="flex items-center gap-2">
            <Check className={shortcut === "enter" ? "text-ink size-3.5" : "size-3.5 opacity-0"} />
            {t("composer.sendShortcut.enter")}
          </span>
        </MenuItem>
        <MenuItem onClick={() => pick("mod_enter")}>
          <span className="flex items-center gap-2">
            <Check className={shortcut === "mod_enter" ? "text-ink size-3.5" : "size-3.5 opacity-0"} />
            {t("composer.sendShortcut.modEnter")}
          </span>
        </MenuItem>
      </Menu>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={t("composer.sendShortcut.label")}
        aria-label={t("composer.sendShortcut.label")}
        className="text-n600 hover:bg-hairsoft hover:text-ink flex size-8 items-center justify-center rounded-full"
      >
        <CornerDownLeft className="size-4" />
      </button>
    </div>
  )
}
