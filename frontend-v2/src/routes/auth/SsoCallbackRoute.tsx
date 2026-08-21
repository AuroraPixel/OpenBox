import { AuthShell, SsoCallback } from "@/features/auth"

export default function SsoCallbackRoute() {
  return (
    <AuthShell>
      <SsoCallback />
    </AuthShell>
  )
}
