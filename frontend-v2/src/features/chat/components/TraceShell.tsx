// The collapsed trace row shared by the process / thinking / tool-chain traces.
// Ported 1:1 from DEEIX-Chat (message-process-trace.tsx and siblings): a
// borderless accordion whose trigger is a two-line block — medium 13px title
// over an 11px muted summary — with the chevron pinned right and rotating on
// open.
import { useState, type ReactNode } from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/shared/lib/cn"

interface Props {
  title: string
  subtitle?: string
  /** This trace is currently producing output. */
  streaming?: boolean
  /** The turn has started answering — collapse a trace that opened itself. */
  autoCollapseReady?: boolean
  children: ReactNode
}

export function TraceShell({ title, subtitle, streaming, autoCollapseReady, children }: Props) {
  // Open/closed is LATCHED, never derived. A turn's activity flags flip many
  // times (tool 1 ends before tool 2 starts; reasoning alternates with tool
  // calls), and deriving `open` from them made the row pop open and shut on
  // every flip — the whole column jumped while streaming. Only two events move
  // the latch: activity starting opens it, and the turn becoming answerable
  // closes it once. Anything else holds the current state, including the
  // user's own toggle.
  const live = Boolean(streaming)
  const ready = Boolean(autoCollapseReady)
  const [open, setOpen] = useState(live)
  const [seen, setSeen] = useState({ live, ready })

  if (seen.live !== live || seen.ready !== ready) {
    setSeen({ live, ready })
    if (live) setOpen(true)
    else if (ready && !seen.ready) setOpen(false)
  }

  return (
    <div className="mb-2 w-full pe-4 sm:pe-6">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group flex w-full items-start justify-between gap-1.5 py-0.5 text-start"
      >
        <span className="min-w-0 flex-1">
          <span className="flex items-center">
            <span
              className={cn(
                "text-md inline-flex min-h-0 w-auto font-medium transition-colors",
                streaming ? "text-shimmer" : "group-hover:text-ink text-n600",
              )}
            >
              {title}
            </span>
          </span>
          {subtitle ? (
            <span className="text-2xs text-n600/62 mt-0.5 block truncate leading-4 font-normal">
              {subtitle}
            </span>
          ) : null}
        </span>
        <ChevronDown
          className={cn(
            "text-n600 group-hover:text-ink mt-0.5 size-3.5 shrink-0 transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      <div className="fold" data-open={open}>
        <div>
          <div className="pt-1.5">{children}</div>
        </div>
      </div>
    </div>
  )
}
