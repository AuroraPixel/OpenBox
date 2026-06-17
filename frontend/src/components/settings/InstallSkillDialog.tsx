import { useState, useRef } from "react"
import { Download, FileText, Loader2, Upload, Archive, X } from "lucide-react"
import { Modal } from "@/components/ui/Modal"
import { api } from "@/services/api"
import { cn } from "@/lib/utils"

const ACCEPTED_FORMATS = ".zip,.tar,.tar.gz,.tgz,.rar"
const FORMAT_LABEL = "ZIP, TAR, TAR.GZ, RAR"

interface InstallSkillDialogProps {
  open: boolean
  onClose: () => void
  onInstalled: () => void
}

export function InstallSkillDialog({ open, onClose, onInstalled }: InstallSkillDialogProps) {
  const [mode, setMode] = useState<"url" | "paste" | "upload">("url")
  const [url, setUrl] = useState("")
  const [name, setName] = useState("")
  const [content, setContent] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [installing, setInstalling] = useState(false)
  const [error, setError] = useState("")
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setMode("url")
    setUrl("")
    setName("")
    setContent("")
    setFile(null)
    setError("")
    setInstalling(false)
    setDragOver(false)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleFile = (f: File) => {
    const ext = f.name.toLowerCase()
    if (!ext.endsWith(".zip") && !ext.endsWith(".tar") && !ext.endsWith(".tar.gz") && !ext.endsWith(".tgz") && !ext.endsWith(".rar")) {
      setError(`Unsupported format. Use ${FORMAT_LABEL}`)
      return
    }
    if (f.size > 50 * 1024 * 1024) {
      setError("File too large (max 50MB)")
      return
    }
    setFile(f)
    setError("")
    // Auto-detect name from filename
    if (!name) {
      let n = f.name
      for (const suffix of [".tar.gz", ".tgz", ".tar", ".zip", ".rar"]) {
        if (n.toLowerCase().endsWith(suffix)) { n = n.slice(0, -suffix.length); break }
      }
      setName(n.replace(/\s+/g, "-"))
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0])
  }

  const handleInstall = async () => {
    setError("")
    setInstalling(true)
    try {
      if (mode === "url") {
        if (!url.trim()) { setError("URL is required"); setInstalling(false); return }
        await api.installSkill({ url: url.trim(), name: name.trim() || undefined })
      } else if (mode === "paste") {
        if (!name.trim()) { setError("Name is required"); setInstalling(false); return }
        if (!content.trim()) { setError("Content is required"); setInstalling(false); return }
        await api.installSkill({ name: name.trim(), content: content.trim() })
      } else if (mode === "upload") {
        if (!file) { setError("Select an archive file"); setInstalling(false); return }
        await api.uploadSkillArchive(file, name.trim() || undefined)
      }
      onInstalled()
      handleClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Install failed")
    } finally {
      setInstalling(false)
    }
  }

  return (
    <Modal open={open} onClose={handleClose} title="Install Skill">
      <div className="p-6 space-y-5 animate-slide-up">
        {/* Mode tabs */}
        <div className="flex gap-1 p-1 rounded-sm bg-[hsl(var(--muted))]/50 border border-[hsl(var(--border))]">
          {([
            { key: "url" as const, icon: Download, label: "From URL" },
            { key: "upload" as const, icon: Archive, label: "Upload Archive" },
            { key: "paste" as const, icon: FileText, label: "Paste Content" },
          ]).map(({ key, icon: Icon, label }) => (
            <button
              key={key}
              onClick={() => setMode(key)}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-sm text-xs font-mono uppercase tracking-wider transition-all cursor-pointer",
                mode === key
                  ? "bg-[hsl(var(--card))] text-[hsl(var(--primary))] border-b-2 border-[hsl(var(--primary))] glow-cyan"
                  : "text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]",
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        {/* URL mode */}
        {mode === "url" && (
          <div className="space-y-4">
            <div>
              <label htmlFor="skill-url" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Repository URL
              </label>
              <input
                id="skill-url"
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/user/skill-repo.git"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
              />
              <p className="text-[11px] text-[hsl(var(--muted-foreground))]/60 mt-1 font-mono">Git repository or .tar.gz archive URL</p>
            </div>
            <div>
              <label htmlFor="skill-name" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Name <span className="opacity-60">(optional)</span>
              </label>
              <input
                id="skill-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Auto-detected from URL"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
              />
            </div>
          </div>
        )}

        {/* Upload mode */}
        {mode === "upload" && (
          <div className="space-y-4">
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={cn(
                "rounded-sm border-2 border-dashed p-8 text-center cursor-pointer transition-all",
                dragOver
                  ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5"
                  : file
                    ? "border-[hsl(var(--success))]/50 bg-[hsl(var(--success))]/5"
                    : "border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/30 hover:bg-[hsl(var(--muted))]/30",
              )}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_FORMATS}
                onChange={(e) => { if (e.target.files?.[0]) handleFile(e.target.files[0]) }}
                className="hidden"
              />
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <Archive className="h-6 w-6 text-[hsl(var(--success))]" />
                  <div className="text-left">
                    <p className="text-sm font-mono font-medium">{file.name}</p>
                    <p className="text-[10px] text-[hsl(var(--muted-foreground))] font-mono">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); setFile(null) }}
                    className="p-1 rounded-sm hover:bg-[hsl(var(--muted))] cursor-pointer"
                  >
                    <X className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                  </button>
                </div>
              ) : (
                <>
                  <Upload className="h-8 w-8 mx-auto mb-2 text-[hsl(var(--muted-foreground))]/40" />
                  <p className="text-sm font-mono text-[hsl(var(--muted-foreground))]">Drop archive here or click to select</p>
                  <p className="text-[10px] text-[hsl(var(--muted-foreground))]/50 font-mono mt-1">{FORMAT_LABEL} (max 50MB)</p>
                </>
              )}
            </div>
            <div>
              <label htmlFor="upload-name" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Name <span className="opacity-60">(optional, auto-detected from filename)</span>
              </label>
              <input
                id="upload-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Auto-detected"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
              />
            </div>
            <p className="text-[10px] text-[hsl(var(--muted-foreground))]/60 font-mono leading-relaxed">
              Archive must contain <code className="px-1 py-0.5 bg-[hsl(var(--muted))] rounded-sm">SKILL.md</code> at root or in <code className="px-1 py-0.5 bg-[hsl(var(--muted))] rounded-sm">.claude/skills/*/SKILL.md</code> structure.
            </p>
          </div>
        )}

        {/* Paste mode */}
        {mode === "paste" && (
          <div className="space-y-4">
            <div>
              <label htmlFor="paste-name" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                Skill Name
              </label>
              <input
                id="paste-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-skill"
                className="w-full px-3 py-2.5 text-sm font-mono rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all"
              />
            </div>
            <div>
              <label htmlFor="paste-content" className="block text-[10px] font-mono uppercase tracking-wider text-[hsl(var(--muted-foreground))] mb-1.5">
                SKILL.md Content
              </label>
              <textarea
                id="paste-content"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={`---\nname: my-skill\ndescription: A custom skill\n---\n\n# My Skill\n\nInstructions here...`}
                rows={10}
                className="w-full px-3 py-2.5 text-sm rounded-sm border border-[hsl(var(--border))] bg-[hsl(var(--surface-1))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]/30 focus:border-[hsl(var(--primary))]/50 transition-all font-mono resize-y"
              />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/20 text-xs text-[hsl(var(--destructive))] font-mono glow-coral">
            <div className="h-1.5 w-1.5 rounded-full bg-[hsl(var(--destructive))] shrink-0" />
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-1">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm border border-[hsl(var(--border))] hover:bg-[hsl(var(--muted))] transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={handleInstall}
            disabled={installing}
            className={cn(
              "px-4 py-2 text-sm font-mono uppercase tracking-wider rounded-sm transition-all cursor-pointer",
              "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]",
              "hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed",
              "flex items-center gap-2 glow-cyan",
            )}
          >
            {installing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Install
          </button>
        </div>
      </div>
    </Modal>
  )
}
