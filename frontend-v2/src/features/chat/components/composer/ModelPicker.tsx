import { useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"
import { Menu } from "@/shared/ui/Menu"
import type { ModelInfo } from "@/shared/types/api"

interface Props {
  models: ModelInfo[]
  activeId?: string
  onPick: (id: string) => void
}

/** The composer's model pill: `⊙ name ▾` opening a checked list. */
export function ModelPicker({ models, activeId, onPick }: Props) {
  const { t } = useTranslation("chat")
  const [open, setOpen] = useState(false)
  const activeName = models.find((m) => m.id === activeId)?.name ?? activeId ?? ""

  return (
    <div className="relative ms-auto">
      <Menu open={open} onClose={() => setOpen(false)} className="end-0 bottom-10 w-60">
        {models.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => {
              onPick(m.id)
              setOpen(false)
            }}
            className="hover:bg-hairsoft flex items-center gap-2.5 rounded-full px-3 py-2 text-start"
          >
            <span className={cn("size-1.5 flex-none rounded-full", m.id === activeId ? "bg-ink" : "bg-n400")} />
            <span className="text-ink min-w-0 flex-1 truncate text-sm">{m.name}</span>
            {m.provider && <span className="text-n600 flex-none text-xs">{m.provider}</span>}
          </button>
        ))}
      </Menu>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={t("model.pick")}
        className="hover:bg-hairsoft flex h-8 items-center gap-2 rounded-full px-3"
      >
        <svg
          aria-hidden
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          className="text-ink"
        >
          <circle cx="12" cy="12" r="7.5" />
          <path d="M6 19 18 5" />
        </svg>
        <span className="text-ink text-sm font-medium">{activeName}</span>
        <span className="text-n600 text-2xs">▾</span>
      </button>
    </div>
  )
}
