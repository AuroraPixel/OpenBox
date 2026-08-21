// Lazy-loaded markdown renderer. Streamdown replaces react-markdown: it
// parses per-block with memoized rendering and tolerates incomplete markdown,
// which is what makes token-by-token streaming render smoothly (the approach
// DEEIX-Chat uses). Typography stays on design tokens; code blocks use the
// built-in shiki highlighter dressed via the shadcn alias tokens.
//
// A `variant` picks one of three tuned component maps (built once per variant,
// memoized): `default` inherits the caller's text-lg/leading-8 prose; `thinking`
// renders smaller, dimmer reasoning with headings demoted to bold paragraphs;
// `user` renders compact bubble prose.
import { useMemo, type ReactNode } from "react"
import { Streamdown, type StreamdownProps } from "streamdown"
import { useTranslation } from "react-i18next"
import CollapsibleCode from "./markdown/CollapsibleCode"

type Components = NonNullable<StreamdownProps["components"]>
type Variant = "default" | "thinking" | "user"

// Per-variant class strings for the block elements that actually differ.
const PROSE = {
  default: {
    p: "mb-3.5 last:mb-0",
    ul: "mb-3.5 flex list-disc flex-col gap-1.5 ps-5 last:mb-0",
    ol: "mb-3.5 flex list-decimal flex-col gap-1.5 ps-5 last:mb-0",
    li: "ps-1 leading-[1.7]",
    strong: "font-medium",
    blockquote: "border-hair text-n700 my-3 border-s-2 ps-4",
  },
  thinking: {
    p: "text-n700 text-md mb-2 leading-[1.75] last:mb-0",
    ul: "text-n700 text-md mb-2 flex list-disc flex-col gap-1 ps-5 last:mb-0",
    ol: "text-n700 text-md mb-2 flex list-decimal flex-col gap-1 ps-5 last:mb-0",
    li: "ps-1 leading-[1.6]",
    strong: "text-n800 font-medium",
    blockquote: "border-hair text-n600 my-2 border-s-2 ps-3",
  },
  user: {
    p: "mb-2 last:mb-0",
    ul: "mb-2 flex list-disc flex-col gap-1 ps-5 last:mb-0",
    ol: "mb-2 flex list-decimal flex-col gap-1 ps-5 last:mb-0",
    li: "ps-1 leading-[1.6]",
    strong: "font-medium",
    blockquote: "border-hair text-n700 my-2 border-s-2 ps-3",
  },
} as const

// Thinking demotes every heading to one bold, tinted paragraph (no h1/h2 tags).
const THINKING_HEADING = "text-n800 text-md mt-1.5 mb-1 font-medium leading-[1.6]"

function headingComponents(variant: Variant): Pick<Components, "h1" | "h2" | "h3" | "h4"> {
  if (variant === "thinking") {
    const P = ({ children }: { children?: ReactNode }) => <p className={THINKING_HEADING}>{children}</p>
    return { h1: P, h2: P, h3: P, h4: P }
  }
  if (variant === "user") {
    return {
      h1: ({ children }) => <h1 className="mt-1 mb-1 text-lg font-medium">{children}</h1>,
      h2: ({ children }) => <h2 className="mt-1 mb-1 text-base font-medium">{children}</h2>,
      h3: ({ children }) => <h3 className="text-md mt-1 mb-1 font-medium">{children}</h3>,
      h4: ({ children }) => <h4 className="text-md mt-1 mb-1 font-medium">{children}</h4>,
    }
  }
  return {
    h1: ({ children }) => <h1 className="mt-2 mb-2.5 text-2xl font-medium tracking-tight">{children}</h1>,
    h2: ({ children }) => <h2 className="mt-2 mb-2 text-xl font-medium tracking-tight">{children}</h2>,
    h3: ({ children }) => <h3 className="mt-1.5 mb-1.5 text-lg font-medium">{children}</h3>,
    h4: ({ children }) => <h4 className="mt-1.5 mb-1 text-base font-medium">{children}</h4>,
  }
}

function buildComponents(variant: Variant): Components {
  const c = PROSE[variant]
  return {
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-a700 hover:text-accent underline underline-offset-2"
      >
        {children}
      </a>
    ),
    p: ({ children }) => <p className={c.p}>{children}</p>,
    ul: ({ children }) => <ul className={c.ul}>{children}</ul>,
    ol: ({ children }) => <ol className={c.ol}>{children}</ol>,
    li: ({ children }) => <li className={c.li}>{children}</li>,
    strong: ({ children }) => <strong className={c.strong}>{children}</strong>,
    blockquote: ({ children }) => <blockquote className={c.blockquote}>{children}</blockquote>,
    ...headingComponents(variant),
    hr: () => <hr className="border-hair my-4 border-t border-none" />,
    pre: ({ children }) => <CollapsibleCode variant={variant}>{children}</CollapsibleCode>,
    table: ({ children }) => (
      <div className="scr border-hair my-3 max-w-165 overflow-x-auto rounded-lg border">
        <table className="text-md w-full border-collapse">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="border-hair bg-rail border-b px-3 py-1.5 text-start font-medium">{children}</th>
    ),
    td: ({ children }) => <td className="border-hair border-b px-3 py-1.5 last:border-b-0">{children}</td>,
  }
}

interface Props {
  text: string
  streaming?: boolean
  variant?: Variant
}

export default function Markdown({ text, streaming, variant = "default" }: Props) {
  const { t } = useTranslation("chat")
  const components = useMemo(() => buildComponents(variant), [variant])
  return (
    <Streamdown
      mode={streaming ? "streaming" : "static"}
      isAnimating={streaming}
      animated
      caret="block"
      parseIncompleteMarkdown
      components={components}
      shikiTheme={["github-light", "github-dark"]}
      controls={{ table: false, code: { copy: true, download: false }, mermaid: false }}
      lineNumbers={variant === "default"}
      translations={{ copyCode: t("copy"), copied: t("copied") }}
    >
      {text}
    </Streamdown>
  )
}
