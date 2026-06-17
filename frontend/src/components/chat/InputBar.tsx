import { useState, useRef, useCallback, useEffect, useMemo } from "react"
import { Send, Square, Paperclip, Slash, AtSign } from "lucide-react"
import { Spinner } from "@/components/ui/Spinner"
import { SlashCommand } from "./SlashCommand"
import { FileMention } from "./FileMention"
import { api } from "@/services/api"
import { useQuery } from "@tanstack/react-query"
import { cn } from "@/lib/utils"

interface InputBarProps {
  onSend: (text: string) => void
  onAbort: () => void
  isBusy?: boolean
  sessionId: string
  statusText?: string
}

// F4: Prompt history — localStorage backed with API sync
const HISTORY_KEY = "openbox_prompt_history"
function loadLocalHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]")
  } catch { return [] }
}
function saveLocalHistory(history: string[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-200)))
  } catch { /* quota exceeded */ }
}

export function InputBar({ onSend, onAbort, isBusy, sessionId, statusText }: InputBarProps) {
  const [text, setText] = useState("")
  const [showSlash, setShowSlash] = useState(false)
  const [showFileMention, setShowFileMention] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // F4: Prompt history state
  const [history, setHistory] = useState<string[]>(() => loadLocalHistory())
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [savedText, setSavedText] = useState("")

  // Load history from API on mount
  useEffect(() => {
    api.getPromptHistory(200).then((items) => {
      if (items && items.length > 0) {
        const apiHistory = items.map((i) => i.content).reverse()
        setHistory((prev) => {
          // Merge: API items not already in local
          const merged = [...new Set([...apiHistory, ...prev])]
          saveLocalHistory(merged)
          return merged
        })
      }
    }).catch(() => {})
  }, [])

  // Fetch first container for file mentions
  const { data: containerData } = useQuery({
    queryKey: ["containers-mention"],
    queryFn: api.listContainers,
    staleTime: 30000,
  })
  const mentionContainerId = containerData?.containers?.find((c: { status: string }) => c.status === "running")?.id || containerData?.containers?.[0]?.id

  // Fetch file list for @ mentions
  const { data: fileData } = useQuery({
    queryKey: ["files-mention", mentionContainerId],
    queryFn: () => api.listFiles(mentionContainerId!, "/workspace"),
    enabled: !!mentionContainerId,
    staleTime: 30000,
  })

  const fileSuggestions = useMemo(() => {
    const files = fileData?.files || []
    const mentionQuery = text.split("@").pop()?.toLowerCase() || ""
    if (!showFileMention) return []
    if (!mentionQuery) return files.map((f: { name: string }) => f.name).slice(0, 10)
    return files
      .map((f: { name: string }) => f.name)
      .filter((name: string) => name.toLowerCase().includes(mentionQuery))
      .slice(0, 10)
  }, [fileData, text, showFileMention])

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = "auto"
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px"
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [text, adjustHeight])

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || isBusy) return

    // Detect slash commands: /command [args]
    if (trimmed.startsWith("/")) {
      const spaceIdx = trimmed.indexOf(" ")
      const command = spaceIdx > 0 ? trimmed.slice(1, spaceIdx) : trimmed.slice(1)
      const args = spaceIdx > 0 ? trimmed.slice(spaceIdx + 1).trim() : undefined
      if (command && !sessionId.startsWith("mock-")) {
        api.executeCommand(sessionId, command, args).catch(() => {
          // Fallback: send as regular message if command execution fails
          onSend(trimmed)
        })
        setText("")
        if (textareaRef.current) textareaRef.current.style.height = "auto"
        return
      }
    }

    // F4: Push to history
    setHistory((prev) => {
      const updated = [...prev, trimmed]
      saveLocalHistory(updated)
      return updated
    })
    setHistoryIndex(-1)
    setSavedText("")

    onSend(trimmed)
    setText("")
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }, [text, isBusy, onSend, sessionId])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
    if (e.key === "Escape" && isBusy) {
      onAbort()
    }
    // F4: Up/Down arrow for prompt history
    if (e.key === "ArrowUp" && !e.shiftKey && history.length > 0) {
      // Only activate when cursor is at the start of text
      const ta = textareaRef.current
      if (ta && ta.selectionStart === 0 && ta.selectionEnd === 0) {
        e.preventDefault()
        if (historyIndex === -1) {
          setSavedText(text)
        }
        const newIndex = historyIndex === -1 ? history.length - 1 : Math.max(0, historyIndex - 1)
        setHistoryIndex(newIndex)
        setText(history[newIndex])
      }
    }
    if (e.key === "ArrowDown" && !e.shiftKey && historyIndex >= 0) {
      const ta = textareaRef.current
      if (ta) {
        e.preventDefault()
        if (historyIndex >= history.length - 1) {
          setHistoryIndex(-1)
          setText(savedText)
        } else {
          const newIndex = historyIndex + 1
          setHistoryIndex(newIndex)
          setText(history[newIndex])
        }
      }
    }
  }, [handleSubmit, isBusy, onAbort, history, historyIndex, text, savedText])

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setText(value)
    // Slash command detection
    if (value === "/" || (value.endsWith("/") && value.charAt(value.length - 2) === " ")) {
      setShowSlash(true)
      setShowFileMention(false)
    } else if (showSlash && !value.includes("/")) {
      setShowSlash(false)
    }
    // @ file mention detection
    if (value.endsWith("@") || (value.includes("@") && !value.endsWith(" "))) {
      const afterAt = value.split("@").pop() || ""
      if (!afterAt.includes(" ")) {
        setShowFileMention(true)
        setShowSlash(false)
      }
    } else {
      setShowFileMention(false)
    }
  }, [showSlash])

  const handleSlashSelect = useCallback((command: string) => {
    setText(command + " ")
    setShowSlash(false)
    textareaRef.current?.focus()
  }, [])

  const handleFileMentionSelect = useCallback((path: string) => {
    // Replace the @query with the selected file path
    const atIdx = text.lastIndexOf("@")
    const before = atIdx >= 0 ? text.slice(0, atIdx) : text
    setText(before + "@" + path + " ")
    setShowFileMention(false)
    textareaRef.current?.focus()
  }, [text])

  const handleAttachClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) { e.target.value = ""; return }

    // Reject binary file types
    const binaryPrefixes = ["image/", "video/", "audio/", "application/pdf", "application/zip", "application/octet-stream"]
    if (file.type && binaryPrefixes.some((p) => file.type.startsWith(p))) {
      e.target.value = ""
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      const content = reader.result as string
      // Check for binary content (null bytes indicate binary)
      if (content.includes("\0")) {
        return
      }
      const maxLen = 50_000
      const truncated = content.length > maxLen
        ? content.slice(0, maxLen) + "\n... (truncated)"
        : content
      const safeName = file.name.replace(/["><]/g, "_")
      const block = `\n<file name="${safeName}">\n${truncated}\n</file>\n`
      setText((prev) => prev + block)
    }
    reader.onerror = () => { /* silently ignore read errors */ }
    reader.readAsText(file)
    // Reset input so the same file can be selected again
    e.target.value = ""
  }, [])

  return (
    <div className="p-2 sm:p-3 pt-1 sm:pt-2">
      <div className="max-w-3xl mx-auto">
        {isBusy && (
          <div className="flex items-center justify-between px-4 py-2.5 mb-2 rounded-sm bg-[hsl(var(--muted))]/60 border border-[hsl(var(--border))]/50">
            <div className="flex items-center gap-2.5 text-sm text-[hsl(var(--muted-foreground))] font-mono">
              <Spinner size="sm" />
              <span className="truncate animate-flicker">{statusText || "Agent is working..."}</span>
            </div>
            <button
              onClick={onAbort}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
                "bg-[hsl(var(--destructive))] text-[hsl(var(--destructive-foreground))] glow-coral",
                "hover:opacity-90 shadow-sm",
              )}
            >
              <Square className="h-3 w-3" />
              Stop
            </button>
          </div>
        )}

        <div className="relative">
          {showSlash && (
            <SlashCommand
              onSelect={handleSlashSelect}
              onClose={() => setShowSlash(false)}
              filter={text.split("/").pop() || ""}
            />
          )}
          {showFileMention && (
            <FileMention
              suggestions={fileSuggestions}
              onSelect={handleFileMentionSelect}
            />
          )}
          <div className={cn(
            "rounded-sm border bg-[hsl(var(--card))] transition-all shadow-sm",
            "border-[hsl(var(--border))]",
            "focus-within:border-[hsl(var(--primary))]/20 focus-within:ring-2 focus-within:ring-[hsl(var(--primary))]/10",
            "focus-within:shadow-[0_0_12px_hsl(var(--primary)/0.15)]",
          )}>
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={isBusy ? "Wait for agent to finish..." : "Send a message..."}
              disabled={isBusy}
              rows={1}
              className="w-full bg-[hsl(var(--surface-1))] text-sm font-mono resize-none focus:outline-none min-h-[24px] max-h-[200px] px-4 pt-3 pb-10 disabled:opacity-50 text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))]/50 rounded-sm"
            />
            <div className="absolute bottom-2.5 left-3 right-3 flex items-center justify-between">
              <div className="flex items-center gap-0.5">
                <button
                  onClick={handleAttachClick}
                  className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
                  title="Attach file"
                  aria-label="Attach file"
                >
                  <Paperclip className="h-3.5 w-3.5" />
                </button>
                <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />
                <button
                  className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
                  onClick={() => setShowSlash(true)}
                  title="Commands"
                  aria-label="Commands"
                >
                  <Slash className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => { setText((prev) => prev + "@"); setShowFileMention(true) }}
                  className="p-1.5 rounded-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--primary))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
                  title="Mention file"
                  aria-label="Mention file"
                >
                  <AtSign className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-[hsl(var(--muted-foreground))] hidden sm:inline font-mono uppercase tracking-wider">
                  <kbd className="px-1 py-0.5 rounded-sm border border-[hsl(var(--border))] text-[9px] font-mono bg-[hsl(var(--muted))]/30">Enter</kbd> send
                  <span className="mx-1 opacity-30">|</span>
                  <kbd className="px-1 py-0.5 rounded-sm border border-[hsl(var(--border))] text-[9px] font-mono bg-[hsl(var(--muted))]/30">Shift+Enter</kbd> newline
                  <span className="mx-1 opacity-30">|</span>
                  <kbd className="px-1 py-0.5 rounded-sm border border-[hsl(var(--border))] text-[9px] font-mono bg-[hsl(var(--muted))]/30">&uarr;</kbd> history
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={!text.trim() || isBusy}
                  className={cn(
                    "p-2 rounded-sm transition-all cursor-pointer",
                    text.trim() && !isBusy
                      ? "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 shadow-[0_0_10px_hsl(var(--primary)/0.4)] animate-glow-pulse"
                      : "text-[hsl(var(--muted-foreground))] opacity-30",
                  )}
                  aria-label="Send message"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
