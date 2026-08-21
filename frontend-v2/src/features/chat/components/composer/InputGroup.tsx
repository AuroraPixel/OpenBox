// The composer shell. It owns focus and drag affordance so the textarea can
// stay chromeless: a global CSS rule strips the textarea's focus ring, and
// this container paints the delicate `focus-within` border in its place —
// replacing the heavy black outline the raw textarea used to draw.
import type { DragEventHandler, ReactNode } from "react"
import { cn } from "@/shared/lib/cn"

interface Props {
  dragging?: boolean
  className?: string
  children: ReactNode
  onDragEnter?: DragEventHandler<HTMLDivElement>
  onDragOver?: DragEventHandler<HTMLDivElement>
  onDragLeave?: DragEventHandler<HTMLDivElement>
  onDrop?: DragEventHandler<HTMLDivElement>
}

export function InputGroup({ dragging, className, children, ...drag }: Props) {
  return (
    <div
      role="group"
      {...drag}
      className={cn(
        "relative flex w-full flex-col rounded-3xl border border-hair bg-card transition-[border-color,box-shadow] duration-150",
        dragging ? "border-dashed border-n500 bg-n200/20" : "focus-within:border-n400",
        className,
      )}
    >
      {children}
    </div>
  )
}
