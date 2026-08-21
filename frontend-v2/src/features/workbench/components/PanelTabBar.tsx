// 52px tab strip: tab pills (glyph + title + close), a "+" to open a new menu
// tab, and the collapse button. Ported from the design reference's tab header.
import { useTranslation } from "react-i18next"
import { Plus, PanelRight, X } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import { usePanelStore } from "@/features/workbench/stores/panel"
import { TAB_GLYPH } from "@/features/workbench/utils/glyphs"
import type { TabKind } from "@/features/workbench/stores/panel"

function useTabTitle() {
  const { t } = useTranslation("workbench")
  return (kind: TabKind) => (kind === "menu" ? t("tabs.new") : t(`tabs.${kind}`))
}

export function PanelTabBar() {
  const { t } = useTranslation("workbench")
  const tabTitle = useTabTitle()
  const tabs = usePanelStore((s) => s.tabs)
  const activeTabId = usePanelStore((s) => s.activeTabId)
  const selectTab = usePanelStore((s) => s.selectTab)
  const closeTab = usePanelStore((s) => s.closeTab)
  const addTab = usePanelStore((s) => s.addTab)
  const togglePanel = usePanelStore((s) => s.togglePanel)

  return (
    <div className="flex h-13 flex-none items-center gap-1.5 px-3">
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden">
        {tabs.map((tb) => {
          const active = tb.id === activeTabId
          return (
            <div
              key={tb.id}
              onClick={() => selectTab(tb.id)}
              className={cn(
                "flex h-8 min-w-0 flex-none cursor-default items-center gap-2 rounded-full border ps-3 pe-2",
                active ? "border-hair bg-card" : "border-transparent hover:bg-hairsoft",
              )}
            >
              <span className="flex-none font-mono text-2xs text-n600">{TAB_GLYPH[tb.kind]}</span>
              <span className="max-w-30 truncate text-xs">{tabTitle(tb.kind)}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  closeTab(tb.id)
                }}
                title={t("action.close", { ns: "common" })}
                aria-label={t("action.close", { ns: "common" })}
                className="flex size-4.5 flex-none items-center justify-center rounded-full text-n600 hover:bg-n200"
              >
                <X size={12} strokeWidth={2.4} />
              </button>
            </div>
          )
        })}
        <button
          type="button"
          onClick={addTab}
          title={t("tabs.new")}
          aria-label={t("tabs.new")}
          className="flex size-7 flex-none items-center justify-center rounded-full text-n700 hover:bg-n200"
        >
          <Plus size={15} strokeWidth={2.6} />
        </button>
      </div>
      <button
        type="button"
        onClick={togglePanel}
        title={t("panel.collapse")}
        aria-label={t("panel.collapse")}
        className="flex size-7.5 flex-none items-center justify-center rounded-full text-n700 hover:bg-n200"
      >
        <PanelRight size={16} strokeWidth={2.4} />
      </button>
    </div>
  )
}
