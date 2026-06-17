import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import { Copy, Check } from "lucide-react"
import { useState, useCallback, useDeferredValue, memo } from "react"

interface TextPartProps {
  text: string
  isStreaming?: boolean
}

const REMARK_PLUGINS = [remarkGfm]
const REHYPE_PLUGINS = [rehypeHighlight]

export const TextPart = memo(function TextPart({ text, isStreaming }: TextPartProps) {
  if (!text) return null
  const deferredText = useDeferredValue(text)

  if (isStreaming) {
    return (
      <pre className="whitespace-pre-wrap text-sm leading-relaxed font-sans">{text}</pre>
    )
  }

  return (
    <div className="markdown-body text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={{
          pre: ({ children, ...props }) => (
            <div className="relative group rounded-sm overflow-hidden">
              <pre {...props}>{children}</pre>
              <CopyButton getText={() => {
                const el = document.createElement("div")
                el.innerHTML = String(children)
                return el.textContent || ""
              }} />
            </div>
          ),
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-[hsl(var(--primary))] hover:text-[hsl(var(--primary))]/80 hover:underline transition-colors glow-cyan">
              {children}
            </a>
          ),
        }}
      >
        {deferredText}
      </ReactMarkdown>
    </div>
  )
})

function CopyButton({ getText }: { getText: () => string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(getText())
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }, [getText])

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2.5 right-2.5 p-1.5 rounded-sm bg-[hsl(var(--muted))]/80 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:bg-[hsl(var(--accent))]/60 shadow-[0_0_6px_hsl(var(--accent)/0.2)] backdrop-blur-sm"
      title="Copy code"
      aria-label="Copy code"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[hsl(var(--success))] glow-green" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}
