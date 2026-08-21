import { Suspense, type ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ToastHost } from "@/shared/ui/Toast"
import { Spinner } from "@/shared/ui/Spinner"

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
})

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={<FullScreenLoader />}>{children}</Suspense>
      <ToastHost />
    </QueryClientProvider>
  )
}

export function FullScreenLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-bg">
      <Spinner className="size-6" />
    </div>
  )
}
