import { AuthShell, LoginForm } from "@/features/auth"

export default function LoginRoute() {
  return (
    <AuthShell>
      <LoginForm />
    </AuthShell>
  )
}
