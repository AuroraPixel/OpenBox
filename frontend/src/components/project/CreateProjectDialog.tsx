import { useEffect, useMemo, useState } from "react"
import { FolderPlus, Loader2 } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { useProjectStore } from "@/stores/project"
import { cn } from "@/lib/utils"
import type { Project } from "@/types"

/**
 * Mirrors the backend's slugify so the directory shown while typing is the one
 * that will actually be created. Kept deliberately simple — the server
 * validates, this only has to be honest about the common case.
 */
function previewSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, "-")
    .replace(/[^a-z0-9._-]/g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 64)
}

export function CreateProjectDialog({
  open, onClose, onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated?: (project: Project) => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const createProject = useProjectStore((s) => s.createProject)

  useEffect(() => {
    if (open) {
      setName("")
      setDescription("")
      setError(null)
      setBusy(false)
    }
  }, [open])

  const slug = useMemo(() => previewSlug(name), [name])
  // A name with no ASCII — a Chinese project name, say — slugifies to nothing.
  // The server generates a slug in that case, so the field is still valid; the
  // preview just cannot promise what the folder will be called.
  const generated = name.trim().length > 0 && slug.length === 0

  const submit = async () => {
    const trimmed = name.trim()
    if (!trimmed || busy) return
    setBusy(true)
    setError(null)
    try {
      const project = await createProject({
        name: trimmed,
        description: description.trim() || undefined,
      })
      onCreated?.(project)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the project")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New project">
      <div className="p-6 space-y-5">
        <p className="text-xs font-mono text-[hsl(var(--muted-foreground))] leading-relaxed">
          A project is a folder in the sandbox. Every session you start in it works on the
          same files, so a new conversation picks up where the last one stopped.
        </p>

        <div>
          <label htmlFor="project-name" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
            Name
          </label>
          <input
            id="project-name"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit() }}
            placeholder="Landing page redesign"
            className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
          />
          <p className="text-[11px] font-mono mt-1.5 text-[hsl(var(--muted-foreground))]/70">
            {name.trim().length === 0 ? (
              <span className="opacity-60">Files will live in /workspace/&lt;folder&gt;</span>
            ) : generated ? (
              <span>Folder name will be generated — <span className="opacity-60">non-Latin names don’t map to a path</span></span>
            ) : (
              <>Files will live in <span className="text-[hsl(var(--primary))]">/workspace/{slug}</span></>
            )}
          </p>
        </div>

        <div>
          <label htmlFor="project-desc" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
            Description <span className="opacity-60">(optional)</span>
          </label>
          <input
            id="project-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit() }}
            placeholder="What this project is for"
            className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
          />
        </div>

        {error && (
          <div className="px-3 py-2 rounded-sm border border-[hsl(var(--destructive))]/30 bg-[hsl(var(--destructive))]/10 text-xs font-mono text-[hsl(var(--destructive))]">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={busy || name.trim().length === 0}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-xs font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
              "hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed",
            )}
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderPlus className="h-3.5 w-3.5" />}
            Create
          </button>
        </div>
      </div>
    </Modal>
  )
}
