import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";

import { AuthShell } from "@/features/auth/components/auth-shell";
import { SignInForm } from "@/features/auth/components/sign-in-form";
import { isLoggedIn } from "@/stores/auth";

export const Route = createFileRoute("/login")({
  beforeLoad: () => {
    if (isLoggedIn()) throw redirect({ to: "/" });
  },
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();

  return (
    <AuthShell title="Welcome back" description="Sign in to continue.">
      <SignInForm onSignedIn={() => void navigate({ to: "/" })} />
    </AuthShell>
  );
}
