import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { CircleCheck, LoaderCircle } from "lucide-react";
import { useState } from "react";

import { Field, FormError, PasswordInput } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AuthShell } from "@/features/auth/components/auth-shell";
import { useAcceptInvitation, useInvitation } from "@/features/users/api";

// The link emailed to a new user: /accept-invite?token=…
export const Route = createFileRoute("/accept-invite")({
  validateSearch: (search): { token: string } => ({
    token: typeof search.token === "string" ? search.token : "",
  }),
  component: AcceptInvitePage,
});

function AcceptInvitePage() {
  const { token } = Route.useSearch();
  const navigate = useNavigate();
  const invitation = useInvitation(token);
  const accept = useAcceptInvitation(token);
  const [password, setPassword] = useState("");

  if (invitation.error) {
    return (
      <AuthShell title="This link can't be used" description={invitation.error.message}>
        <Button asChild variant="outline">
          <Link to="/login">Go to sign in</Link>
        </Button>
      </AuthShell>
    );
  }

  if (!invitation.data) {
    return (
      <AuthShell title="Confirm your account">
        <div className="grid gap-3">
          <Skeleton className="h-11 w-full" />
          <Skeleton className="h-11 w-full" />
        </div>
      </AuthShell>
    );
  }

  const { realm_name, email, needs_password } = invitation.data;

  if (accept.data && !accept.data.signed_in) {
    return (
      <AuthShell
        title="You're in"
        description={`You now have access to ${realm_name}. Sign in with your existing password.`}
      >
        <Button asChild size="lg" className="h-11 w-full text-sm">
          <Link to="/login">
            <CircleCheck /> Sign in
          </Link>
        </Button>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Confirm your account"
      description={
        <>
          You've been added to <span className="font-medium text-foreground">{realm_name}</span> as{" "}
          <span className="font-medium text-foreground">{email}</span>.
          {needs_password && " Choose a password to finish."}
        </>
      }
    >
      <form
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          accept.mutate(needs_password ? password : null, {
            onSuccess: (result) => {
              if (result.signed_in) void navigate({ to: "/" });
            },
          });
        }}
      >
        {needs_password && (
          <Field
            label="Password"
            htmlFor="new-password"
            hint="At least 12 characters, and not a common password."
          >
            <PasswordInput
              id="new-password"
              autoComplete="new-password"
              autoFocus
              minLength={12}
              className="h-11 bg-card px-3.5 text-base md:text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
        )}

        <FormError error={accept.error} />

        <Button type="submit" size="lg" className="h-11 text-sm" disabled={accept.isPending}>
          {accept.isPending && <LoaderCircle aria-hidden className="animate-spin" />}
          {needs_password ? "Set password and sign in" : "Confirm"}
        </Button>
      </form>
    </AuthShell>
  );
}
