import { createFileRoute } from "@tanstack/react-router";

import { SettingsSection } from "@/components/settings-section";
import { Skeleton } from "@/components/ui/skeleton";
import { PasswordForm } from "@/features/account/components/password-form";
import { useMe } from "@/features/auth/api";

export const Route = createFileRoute("/_app/account/")({
  component: MySettingsPage,
});

/** My own settings (0002), for everyone: about me, not the company. One section each. */
function MySettingsPage() {
  const me = useMe();
  return (
    <div className="mx-auto w-full max-w-3xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">My settings</h1>
      {me.data ? (
        <p className="mt-1 text-sm break-words text-muted-foreground">
          Signed in as <span className="font-medium text-foreground">{me.data.email}</span>
        </p>
      ) : (
        <Skeleton className="mt-2 h-5 w-56" />
      )}

      <div className="mt-6 grid gap-6">
        <SettingsSection
          title="Password"
          description="Changing it signs you out everywhere else. You stay signed in here."
        >
          <PasswordForm />
        </SettingsSection>
      </div>
    </div>
  );
}
