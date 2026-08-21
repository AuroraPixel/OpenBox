// Presentational overlay for the composer's @ / mention menu. Renders in-flow
// above the input row — the parent element must be `relative`. All state comes
// from useMentionMenu; this component only paints sections and forwards intent.
//
// Wiring:
//   const mention = useMentionMenu({ ... })
//   ...
//   <div className="relative">
//     {mention.open && (
//       <MentionMenu
//         sections={mention.sections}
//         activeIndex={mention.activeIndex}
//         onActiveIndexChange={mention.setActiveIndex}
//         onSelect={mention.select}
//       />
//     )}
//     <textarea ... />
//   </div>
//
// Items use onMouseDown+preventDefault so clicking never blurs the textarea
// (the caret restore in useMentionMenu.select depends on the focus staying put).
import { useTranslation } from "react-i18next"
import { FileText } from "lucide-react"
import { cn } from "@/shared/lib/cn"
import type { MentionItem, MentionItemKind, MentionSection } from "../../hooks/useMentionMenu"

interface Props {
  sections: MentionSection[]
  activeIndex: number
  onActiveIndexChange: (index: number) => void
  onSelect: (item: MentionItem) => void
}

const SECTION_LABEL: Record<MentionItemKind, string> = {
  file: "files",
  skill: "skills",
  command: "commands",
}

/** Middle-truncate a path, keeping the head and (longer) tail readable. */
function shortenPath(path: string, head = 14, tail = 28): string {
  if (path.length <= head + tail + 1) return path
  return `${path.slice(0, head)}…${path.slice(path.length - tail)}`
}

/** Flat-list start index of `sections[index]` (for keyboard-nav offsets). */
function sectionBase(sections: MentionSection[], index: number): number {
  let n = 0
  for (let i = 0; i < index; i++) n += sections[i].items.length
  return n
}

export function MentionMenu({ sections, activeIndex, onActiveIndexChange, onSelect }: Props) {
  const { t } = useTranslation("chat")

  return (
    <div
      role="listbox"
      className="scr absolute bottom-full inset-x-0 z-50 mb-2 max-h-72 overflow-auto rounded-xl border border-hair bg-card p-1.5 shadow-pop"
    >
      {sections.map((section, sectionIndex) => {
        const base = sectionBase(sections, sectionIndex)
        return (
          <div key={section.kind}>
            <div className="px-2.5 pt-1.5 pb-1 text-2xs font-medium text-n600">
              {t(`composer.mention.${SECTION_LABEL[section.kind]}`)}
            </div>
            {section.needSandbox ? (
              <p className="px-2.5 py-1.5 text-2xs text-n600">{t("composer.mention.needSandbox")}</p>
            ) : section.loading ? (
              <p className="px-2.5 py-1.5 text-2xs text-n600">{t("composer.mention.loading")}</p>
            ) : section.items.length === 0 ? (
              <p className="px-2.5 py-1.5 text-2xs text-n600">{t("composer.mention.empty")}</p>
            ) : (
              section.items.map((item, i) => {
                const index = base + i
                const active = index === activeIndex
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      onSelect(item)
                    }}
                    onMouseEnter={() => onActiveIndexChange(index)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-start text-md",
                      active && "bg-hairsoft",
                    )}
                  >
                    {item.kind === "file" ? (
                      <>
                        <FileText className="size-4 flex-none text-n500" strokeWidth={1.8} />
                        <span className="min-w-0 flex-1 truncate font-mono text-xs text-ink">
                          {shortenPath(item.label)}
                        </span>
                      </>
                    ) : (
                      <span className="flex min-w-0 flex-1 items-baseline gap-2">
                        <span className="flex-none text-ink">{item.label}</span>
                        {item.description && (
                          <span className="min-w-0 flex-1 truncate text-2xs text-n600">
                            {item.description}
                          </span>
                        )}
                      </span>
                    )}
                  </button>
                )
              })
            )}
          </div>
        )
      })}
    </div>
  )
}
