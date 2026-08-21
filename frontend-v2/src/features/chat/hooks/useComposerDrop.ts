// Drag-and-drop file intake for the composer. dragenter/dragleave fire once
// per child element, so a nesting counter keeps the dashed state from
// flickering as the cursor crosses inner nodes. Inert unless `enabled`
// (no running sandbox = nowhere to upload).
import { useCallback, useRef, useState } from "react"
import type { DragEvent } from "react"

interface Options {
  enabled: boolean
  onFiles: (files: File[]) => void
}

export function useComposerDrop({ enabled, onFiles }: Options) {
  const [dragging, setDragging] = useState(false)
  const depth = useRef(0)

  const onDragEnter = useCallback(
    (e: DragEvent<HTMLElement>) => {
      if (!enabled) return
      if (![...e.dataTransfer.types].includes("Files")) return
      e.preventDefault()
      depth.current += 1
      setDragging(true)
    },
    [enabled],
  )

  const onDragOver = useCallback(
    (e: DragEvent<HTMLElement>) => {
      if (!enabled) return
      if (![...e.dataTransfer.types].includes("Files")) return
      e.preventDefault()
      e.dataTransfer.dropEffect = "copy"
    },
    [enabled],
  )

  const onDragLeave = useCallback(
    (e: DragEvent<HTMLElement>) => {
      if (!enabled) return
      e.preventDefault()
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setDragging(false)
    },
    [enabled],
  )

  const onDrop = useCallback(
    (e: DragEvent<HTMLElement>) => {
      if (!enabled) return
      e.preventDefault()
      depth.current = 0
      setDragging(false)
      const files = [...e.dataTransfer.files]
      if (files.length > 0) onFiles(files)
    },
    [enabled, onFiles],
  )

  return { dragging, dragHandlers: { onDragEnter, onDragOver, onDragLeave, onDrop } }
}
