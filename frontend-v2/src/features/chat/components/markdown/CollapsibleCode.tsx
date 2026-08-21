// `pre` override for streamdown code blocks. Streamdown's own `code` renderer
// still does the shiki highlighting and copy button (it fires when the child
// carries data-block="true"); this wrapper only clones that child through and,
// for long blocks, folds it to a fixed height with a bottom fade + a toggle.
import { cloneElement, isValidElement, useState, type ReactElement, type ReactNode } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { useTranslation } from "react-i18next"
import { cn } from "@/shared/lib/cn"

// Blocks taller than this collapse by default; short snippets render untouched.
const LINE_THRESHOLD = 20

type CodeChildProps = {
  children?: ReactNode
  className?: string
  "data-block"?: string
}

type Variant = "default" | "thinking" | "user"

interface Props {
  children?: ReactNode
  variant?: Variant
}

function readCodeText(child: ReactElement<CodeChildProps>): string {
  const raw = child.props.children
  if (typeof raw === "string") return raw
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === "string").join("")
  return ""
}

function countLines(value: string): number {
  if (!value) return 0
  return value.replace(/\n$/, "").split("\n").length
}

export default function CollapsibleCode({ children, variant = "default" }: Props) {
  const { t } = useTranslation("chat")
  const [expanded, setExpanded] = useState(false)

  if (!isValidElement<CodeChildProps>(children)) return <>{children}</>

  // Cloning with data-block flips streamdown's code renderer into block mode
  // (shiki highlight + copy control), matching its default `pre` behaviour.
  const codeBlock = cloneElement(children, { "data-block": "true" })
  const lines = countLines(readCodeText(children))
  const collapsible = lines > LINE_THRESHOLD

  // User bubbles want a flat, inline-feeling block: drop the border, tint the body.
  const bodyClass =
    variant === "user"
      ? "[&_[data-streamdown='code-block-body']]:border-0 [&_[data-streamdown='code-block-body']]:bg-n300/40"
      : undefined

  if (!collapsible) {
    return <div className={cn("relative w-full", bodyClass)}>{codeBlock}</div>
  }

  return (
    <div className={cn("relative w-full", bodyClass)}>
      <div className={cn("relative w-full", !expanded && "max-h-80 overflow-hidden")}>
        {codeBlock}
        {!expanded ? (
          <div className="to-card pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-b from-transparent" />
        ) : null}
      </div>
      <div className="mt-1 flex justify-center">
        <button
          type="button"
          onClick={() => setExpanded((current) => !current)}
          className="text-n600 hover:bg-n200/60 hover:text-n800 text-2xs inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 font-medium transition-colors"
        >
          {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          <span>{expanded ? t("markdown.collapseCode") : t("markdown.expandCode")}</span>
          <span className="text-n500">{t("markdown.lines", { count: lines })}</span>
        </button>
      </div>
    </div>
  )
}
