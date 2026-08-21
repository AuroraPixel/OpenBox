import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router/dom"
import "@/styles/index.css"
import "@/shared/i18n"
import "@/shared/appearance/store"
import { refreshAccessToken } from "@/shared/api/auth-store"
import { AppProviders } from "@/app/providers/AppProviders"
import { router } from "@/app/router/router"

// Try restoring the session from the refresh cookie before first paint state
// settles; guards render a loader while this is in flight.
void refreshAccessToken()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)
