// Terminal tab: picks the running sandbox, or offers to create one. The xterm
// terminal itself lives in a lazily-loaded chunk (TerminalView) so @xterm/* and
// its CSS never enter the main bundle.
import { Suspense, lazy } from "react"
import { useTranslation } from "react-i18next"
import { useCreateContainer, useRunningContainer } from "@/features/workbench/api/containers"
import { EmptyState } from "./EmptyState"

const TerminalView = lazy(() => import("./TerminalView"))

export function TerminalTab() {
  const { t } = useTranslation("workbench")
  const running = useRunningContainer()
  const create = useCreateContainer()

  if (!running) {
    return (
      <EmptyState
        title={t("terminal.empty")}
        hint={t("terminal.emptyHint")}
        action={{
          label: t("sandbox.create"),
          onClick: () => create.mutate(undefined),
          pending: create.isPending,
        }}
      />
    )
  }

  return (
    <div className="mx-3 mb-3 min-h-0 flex-1 overflow-hidden rounded-xl bg-term p-2">
      <Suspense fallback={<div className="p-3 text-sm text-termink">{t("terminal.connecting")}</div>}>
        <TerminalView containerId={running.id} />
      </Suspense>
    </div>
  )
}
