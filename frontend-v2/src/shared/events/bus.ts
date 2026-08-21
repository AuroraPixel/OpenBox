// In-app event bus for cross-feature signals (ENGINEERING_SPEC §4.2 事件解耦).
// Chat emits "open review" — workbench listens. Neither imports the other.
type AppEventMap = {
  "workbench.open": { kind: "review" | "terminal" | "browser" | "files"; file?: string }
}

type AppEventName = keyof AppEventMap
type Handler<E extends AppEventName> = (data: AppEventMap[E]) => void

const handlers = new Map<string, Set<Handler<AppEventName>>>()

export function onAppEvent<E extends AppEventName>(event: E, handler: Handler<E>): () => void {
  const set = handlers.get(event) ?? new Set()
  set.add(handler as Handler<AppEventName>)
  handlers.set(event, set)
  return () => set.delete(handler as Handler<AppEventName>)
}

export function emitAppEvent<E extends AppEventName>(event: E, data: AppEventMap[E]): void {
  handlers.get(event)?.forEach((h) => h(data))
}
