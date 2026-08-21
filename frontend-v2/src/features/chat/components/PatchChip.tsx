import { DiffPreview } from "./DiffPreview"
import type { FilePart, PatchPart } from "@/shared/types/api"

interface PatchChipProps {
  part: PatchPart
  sessionId: string
}

/** Changed-files list for one step. The counts ride along on the patch part
 *  itself, so this needs no diff request — the panel fetches the real hunks
 *  once, when the user opens one. */
export function PatchChip({ part, sessionId }: PatchChipProps) {
  return (
    <div className="flex flex-col">
      {part.files.map((f) => (
        <DiffPreview key={f.path} file={f} sessionId={sessionId} />
      ))}
    </div>
  )
}

/** A produced-file reference (file part) — a lightweight mono chip. */
export function FileChip({ part }: { part: FilePart }) {
  const name = part.path.split("/").pop() ?? part.path
  return (
    <div className="border-hair flex items-center gap-2.5 self-start rounded-full border px-4 py-2">
      <span className="bg-s400 size-2 rounded-full" />
      <span className="text-ink font-mono text-sm">{name}</span>
    </div>
  )
}
