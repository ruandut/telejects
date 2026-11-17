import { createFileRoute } from "@tanstack/react-router";

import { useMe } from "@/features/auth/api";

export const Route = createFileRoute("/_app/")({
  component: DashboardPage,
});

function DashboardPage() {
  const me = useMe();
  const firstName = me.data?.name.includes("@") ? null : me.data?.name.split(" ")[0];

  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
        Welcome{firstName ? `, ${firstName}` : ""}
      </h1>
      <p className="mt-2 max-w-prose text-sm text-muted-foreground">
        Nothing here yet. Screens arrive with the specs.
      </p>
    </div>
  );
}
