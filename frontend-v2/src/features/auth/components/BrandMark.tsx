import { Link } from "react-router"
import { paths } from "@/shared/router/paths"

/** The bossip logo lockup: rounded "b" tile + shine wordmark. Links home. */
export function BrandMark({ dot = false }: { dot?: boolean }) {
  return (
    <Link to={paths.landing} className="flex flex-none select-none items-center gap-2.5">
      <span className="relative flex size-6.5 items-center justify-center rounded-lg bg-ink">
        <span className="mt-px text-base font-bold leading-none text-bg">b</span>
        {dot && <span className="absolute -end-px -top-px size-1.5 rounded-full bg-n400 ring-2 ring-bg" />}
      </span>
      <span className="wordmark text-xl font-bold tracking-tight">bossip</span>
    </Link>
  )
}
