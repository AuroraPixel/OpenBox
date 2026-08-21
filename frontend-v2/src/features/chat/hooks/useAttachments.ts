// Composer attachments. Preferred route: browser → OSS on a presigned PUT
// (bytes never squeeze through the backend or the sandbox tunnel; the desktop
// pulls from OSS when the message is sent). When OSS isn't configured the
// backend answers 503 and we fall back to the legacy chunked upload straight
// into the sandbox. Either way the sent message carries sandbox paths.
import { useCallback, useEffect, useRef, useState } from "react"
import { env } from "@/shared/config/env"
import { ApiError } from "@/shared/api/http"
import { useAuthStore } from "@/shared/api/auth-store"
import { completeAsset, createAsset, putToOss } from "../api/assets"

export interface PendingAttachment {
  id: string
  name: string
  size: number
  mime: string
  status: "uploading" | "done" | "error"
  /** 0..1 while uploading to OSS. */
  progress: number
  /** Object URL for image thumbnails in the composer strip. */
  preview?: string
  /** Where the file lands in the sandbox (message contract). */
  path?: string
  /** file_assets id when the OSS route was used. */
  assetId?: string
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

/** Legacy route: chunked upload through the backend into the sandbox. */
async function uploadViaSandbox(containerId: string, file: File): Promise<{ path: string }> {
  const form = new FormData()
  form.append("file", file)
  const token = useAuthStore.getState().accessToken
  const res = await fetch(`${env.apiBase}/api/containers/${containerId}/files/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
    credentials: "include",
  })
  if (!res.ok) throw new Error(await res.text())
  return (await res.json()) as { path: string }
}

export function useAttachments(containerId: string | null, sessionId?: string | null) {
  const [items, setItems] = useState<PendingAttachment[]>([])
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  // Object URLs live until the hook unmounts; cheap and simple.
  const previewsRef = useRef<string[]>([])
  useEffect(
    () => () => {
      for (const url of previewsRef.current) URL.revokeObjectURL(url)
    },
    [],
  )

  const addFiles = useCallback(
    (input: File[]) => {
      if (input.length === 0) return
      const files = withNames(input)
      for (const file of files) {
        const id = `att-${++seq}`
        const mime = file.type || "application/octet-stream"
        let preview: string | undefined
        if (mime.startsWith("image/")) {
          preview = URL.createObjectURL(file)
          previewsRef.current.push(preview)
        }
        setItems((list) => [
          ...list,
          { id, name: file.name, size: file.size, mime, status: "uploading", progress: 0, preview },
        ])
        const patch = (update: Partial<PendingAttachment>) =>
          setItems((list) => list.map((a) => (a.id === id ? { ...a, ...update } : a)))

        void (async () => {
          try {
            const ticket = await createAsset(file.name, mime, file.size, sessionId)
            await putToOss(ticket, file, (fraction) => patch({ progress: fraction }))
            const info = await completeAsset(ticket.id)
            patch({ status: "done", progress: 1, path: info.sandboxPath, assetId: info.id, name: info.name })
          } catch (err) {
            // 503 = OSS transfer not configured → legacy sandbox upload.
            if (err instanceof ApiError && err.status === 503 && containerId) {
              try {
                const data = await uploadViaSandbox(containerId, file)
                patch({ status: "done", progress: 1, path: data.path })
                return
              } catch {
                // fall through to the error state
              }
            }
            patch({ status: "error" })
          }
        })()
      }
    },
    [containerId, sessionId],
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

  /** OSS asset ids for the prompt body — the backend pulls them into the
   *  sandbox before the agent starts and pins file parts on the message. */
  const assetIds = useCallback(
    (): string[] =>
      itemsRef.current.filter((a) => a.status === "done" && a.assetId).map((a) => a.assetId as string),
    [],
  )

  const uploading = items.some((a) => a.status === "uploading")
  return { items, addFiles, remove, clear, decorate, assetIds, uploading }
}
