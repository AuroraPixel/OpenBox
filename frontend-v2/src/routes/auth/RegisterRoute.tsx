import { AuthShell, RegisterForm } from "@/features/auth"

export default function RegisterRoute() {
  return (
    <AuthShell>
      <RegisterForm />
    </AuthShell>
  )
}
