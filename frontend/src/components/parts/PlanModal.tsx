import { useState, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import { Pencil, Save, X, Loader2, FileText, Check } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { api } from "@/services/api"
import { useSessionStore } from "@/stores/session"
import type { PlanStatus } from "@/types"

interface PlanModalProps {
  open: boolean
  onClose: () => void
  content: string
  path: string
  status: PlanStatus
  sessionId: string
  onRefresh: () => void
  onAccept?: () => void
  onReject?: () => void
}

export function PlanModal({ open, onClose, content, path, status, sessionId, onRefresh, onAccept, onReject }: PlanModalProps) {
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState("")
  const [saving, setSaving] = useState(false)
  const notifyPlanUpdated = useSessionStore((s) => s.notifyPlanUpdated)

  const canEdit = status === "writing" || status === "ready"
  const relPath = path.replace("/workspace/", "")

  const handleEdit = useCallback(() => {
    setEditContent(content)
    setEditing(true)
  }, [content])

  const handleCancel = useCallback(() => {
    setEditing(false)
    setEditContent("")
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await api.updatePlan(sessionId, editContent)
      setEditing(false)
      notifyPlanUpdated(sessionId)
      onRefresh()
    } catch {
      // TODO: error handling
    } finally {
      setSaving(false)
    }
  }, [sessionId, editContent, notifyPlanUpdated, onRefresh])

  const handleClose = useCallback(() => {
    if (editing) {
      setEditing(false)
      setEditContent("")
    }
    onClose()
  }, [editing, onClose])

  const handleAccept = useCallback(() => {
    onClose()
    onAccept?.()
  }, [onClose, onAccept])

  const handleReject = useCallback(() => {
    onClose()
    onReject?.()
  }, [onClose, onReject])

  return (
    <Modal
      open={open}
      onClose={handleClose}
      className="w-[90vw] max-w-4xl max-h-[85vh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[hsl(var(--border))]/30 shrink-0 bg-[hsl(var(--card))]">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex items-center justify-center h-6 w-6 rounded-sm bg-[hsl(var(--primary))]/10 shadow-[0_0_6px_hsl(var(--primary)/0.2)]">
            <FileText className="h-3.5 w-3.5 text-[hsl(var(--primary))] glow-cyan" />
          </div>
          <span className="text-sm font-display font-semibold truncate text-[hsl(var(--primary))]">Plan</span>
          <span className="text-xs font-mono text-[hsl(var(--accent))]/80 truncate">{relPath}</span>
        </div>
        <div className="flex items-center gap-2.5 shrink-0">
          {editing ? (
            <>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 disabled:opacity-50 cursor-pointer shadow-[0_0_8px_hsl(var(--primary)/0.3)] transition-opacity"
              >
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                Save
              </button>
              <button
                onClick={handleCancel}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 cursor-pointer transition-colors"
              >
                Cancel
              </button>
            </>
          ) : canEdit ? (
            <button
              onClick={handleEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 cursor-pointer transition-colors"
            >
              <Pencil className="h-3 w-3" />
              Edit
            </button>
          ) : null}
          <button
            onClick={handleClose}
            className="p-1.5 rounded-sm hover:bg-[hsl(var(--muted))]/60 transition-colors cursor-pointer"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="overflow-y-auto flex-1 bg-[hsl(var(--background))]">
        {editing ? (
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="w-full h-full min-h-[60vh] p-6 bg-[hsl(var(--terminal-bg))] text-[hsl(var(--foreground))] text-sm font-mono resize-none outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/20 transition-shadow"
            spellCheck={false}
            autoFocus
          />
        ) : (
          <div className="p-6 max-w-3xl mx-auto">
            {content ? (
              <div className="markdown-body text-sm leading-relaxed">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                  components={{
                    a: ({ href, children }) => (
                      <a href={href} target="_blank" rel="noopener noreferrer" className="text-[hsl(var(--primary))] hover:text-[hsl(var(--primary))]/80 hover:underline transition-colors glow-cyan">
                        {children}
                      </a>
                    ),
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-[hsl(var(--muted-foreground))] gap-3">
                <div className="flex items-center justify-center h-12 w-12 rounded-sm bg-[hsl(var(--surface-1))]">
                  <FileText className="h-6 w-6 opacity-40" />
                </div>
                <p className="text-sm font-mono uppercase tracking-wider">No plan content yet</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer: Accept / Reject buttons when plan is ready */}
      {status === "ready" && !editing && (
        <div className="flex items-center justify-end gap-2.5 px-6 py-4 border-t border-[hsl(var(--border))]/30 shrink-0 bg-[hsl(var(--card))]">
          <button
            onClick={handleReject}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))]/60 cursor-pointer transition-colors"
          >
            <X className="h-3 w-3" />
            Reject & Regenerate
          </button>
          <button
            onClick={handleAccept}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-sm text-xs font-mono uppercase tracking-wider bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:opacity-90 cursor-pointer shadow-[0_0_8px_hsl(var(--primary)/0.3)] transition-opacity"
          >
            <Check className="h-3 w-3" />
            Accept & Build
          </button>
        </div>
      )}
    </Modal>
  )
}
