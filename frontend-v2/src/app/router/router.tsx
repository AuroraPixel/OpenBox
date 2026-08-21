import { lazy } from "react"
import { createBrowserRouter } from "react-router"
import { AppErrorBoundary } from "@/app/router/AppErrorBoundary"
import { RequireAuth, RedirectIfAuthed } from "@/app/router/guards"
import { routePatterns, paths } from "@/app/router/paths"

const LandingRoute = lazy(() => import("@/routes/landing/LandingRoute"))
const LoginRoute = lazy(() => import("@/routes/auth/LoginRoute"))
const RegisterRoute = lazy(() => import("@/routes/auth/RegisterRoute"))
const SsoCallbackRoute = lazy(() => import("@/routes/auth/SsoCallbackRoute"))
const WorkspaceLayout = lazy(() => import("@/app/layouts/WorkspaceLayout"))
const EmptyChatRoute = lazy(() => import("@/routes/workspace/EmptyChatRoute"))
const ChatRoute = lazy(() => import("@/routes/workspace/ChatRoute"))
const SettingsRoute = lazy(() => import("@/routes/settings/SettingsRoute"))
const NotFoundRoute = lazy(() => import("@/routes/NotFoundRoute"))

export const router = createBrowserRouter([
  {
    errorElement: <AppErrorBoundary />,
    children: [
      { path: paths.landing, element: <LandingRoute /> },
      {
        path: paths.login,
        element: (
          <RedirectIfAuthed>
            <LoginRoute />
          </RedirectIfAuthed>
        ),
      },
      {
        path: paths.register,
        element: (
          <RedirectIfAuthed>
            <RegisterRoute />
          </RedirectIfAuthed>
        ),
      },
      { path: paths.ssoCallback, element: <SsoCallbackRoute /> },
      {
        path: paths.app,
        element: (
          <RequireAuth>
            <WorkspaceLayout />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <EmptyChatRoute /> },
          { path: routePatterns.chat, element: <ChatRoute /> },
          { path: routePatterns.settings, element: <SettingsRoute /> },
        ],
      },
      { path: "*", element: <NotFoundRoute /> },
    ],
  },
])
