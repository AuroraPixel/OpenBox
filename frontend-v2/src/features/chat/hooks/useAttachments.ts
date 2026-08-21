// Composer attachments: files upload straight into the session sandbox
// (/workspace/uploads) so the agent can read them; the sent message carries
// the landed paths.
import { useCallback, useEffect, useRef, useState } from "react"
import { env } from "@/shared/config/env"
import { useAuthStore } from "@/shared/api/auth-store"

export interface PendingAttachment {
  id: string
  name: string
  size: number
  status: "uploading" | "done" | "error"
  path?: string
}

let seq = 0

/** Give clipboard/drop payloads a real filename — screenshots arrive nameless
 *  as `image/png` blobs, so the sandbox needs something to land them under. */
function withNames(files: File[]): File[] {
  const ts = Date.now()
  return files.map((file, i) => {
    if (file.name.trim()) return file
    const image = file.type.startsWith("image/")
    const prefix = image ? "pasted-image" : "pasted-file"
    const ext = image ? "png" : "bin"
    const suffix = files.length > 1 ? `-${i + 1}` : ""
    return new File([file], `${prefix}-${ts}${suffix}.${ext}`, {
      type: file.type,
      lastModified: file.lastModified,
    })
  })
}

export function useAttachments(containerId: string | null) {
  const [items, setItems] = useState<PendingAttachment[]>([])
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const addFiles = useCallback(
    (input: File[]) => {
      if (!containerId || input.length === 0) return
      const files = withNames(input)
      for (const file of files) {
        const id = `att-${++seq}`
        setItems((list) => [
          ...list,
          { id, name: file.name, size: file.size, status: "uploading" },
        ])
        const form = new FormData()
        form.append("file", file)
        const token = useAuthStore.getState().accessToken
        void fetch(`${env.apiBase}/api/containers/${containerId}/files/upload`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: form,
          credentials: "include",
        })
          .then(async (res) => {
            if (!res.ok) throw new Error(await res.text())
            const data = (await res.json()) as { path: string; name: string }
            setItems((list) =>
              list.map((a) => (a.id === id ? { ...a, status: "done", path: data.path } : a)),
            )
          })
          .catch(() => {
            setItems((list) => list.map((a) => (a.id === id ? { ...a, status: "error" } : a)))
          })
      }
    },
    [containerId],
  )

  const remove = useCallback((id: string) => {
    setItems((list) => list.filter((a) => a.id !== id))
  }, [])

  const clear = useCallback(() => setItems([]), [])

  /** Appends landed sandbox paths to the outgoing message text. */
  const decorate = useCallback((text: string): string => {
    const paths = itemsRef.current.filter((a) => a.status === "done" && a.path).map((a) => a.path)
    if (paths.length === 0) return text
    return `${text}\n\n[attachments]\n${paths.map((p) => `- ${p}`).join("\n")}`
  }, [])

  const uploading = items.some((a) => a.status === "uploading")
  return { items, addFiles, remove, clear, decorate, uploading }
}
