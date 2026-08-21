// Assistant placeholder while a turn is streaming but has produced no prose
// yet — ported from DEEIX-Chat's AssistantMessageSkeleton.
export function StreamSkeleton() {
  return (
    <div className="w-full max-w-170 space-y-2.5 pt-1" aria-hidden>
      <span className="bg-n200 block h-4 w-[72%] animate-pulse rounded-full" />
      <span className="bg-n200 block h-4 w-[88%] animate-pulse rounded-full" />
      <span className="bg-n200 block h-4 w-[54%] animate-pulse rounded-full" />
    </div>
  )
}
