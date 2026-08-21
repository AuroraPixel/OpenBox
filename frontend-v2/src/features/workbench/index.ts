// Public surface of the workbench feature.
//   - WorkbenchPanel: the right-hand work panel (mount in the workspace layout).
//   - usePanelStore:  layout reads `open` to decide whether to render the panel.
//   - usePanelEvents: mount once so chat "审阅" clicks + `session.diff` are wired.
export { WorkbenchPanel } from "./components/WorkbenchPanel"
export { usePanelStore } from "./stores/panel"
export { usePanelEvents } from "./hooks/usePanelEvents"
