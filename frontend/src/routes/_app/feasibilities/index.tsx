import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, Plus } from "lucide-react";

import { NoAccess } from "@/components/no-access";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useRuns } from "@/features/feasibilities/api";
import { Progress, RunStatusBadge } from "@/features/feasibilities/components/status";
import { usePermission } from "@/features/realms/permissions";

export const Route = createFileRoute("/_app/feasibilities/")({
  component: FeasibilitiesPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short" });

function FeasibilitiesPage() {
  const me = useMe();
  const canView = usePermission("feasibilities.view");
  if (me.data && !canView) return <NoAccess section="Feasibilities" />;
  return <Runs />;
}

function Runs() {
  const runs = useRuns();
  const canRun = usePermission("feasibilities.run");
  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Feasibilities</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Check a list of sites against your providers' products.
          </p>
        </div>
        {canRun && (
          <Button asChild>
            <Link to="/feasibilities/new">
              <Plus /> New run
            </Link>
          </Button>
        )}
      </div>
      <div className="mt-6">
        {runs.data ? (
          runs.data.length ? (
            <ul className="grid gap-2">
              {runs.data.map((run) => (
                <li key={run.id}>
                  <Link
                    to="/feasibilities/$runId"
                    params={{ runId: String(run.id) }}
                    className="flex items-center gap-3 rounded-xl border bg-card p-4 outline-none hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <div className="grid min-w-0 flex-1 gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-medium">{run.name}</span>
                        <RunStatusBadge status={run.status} />
                      </div>
                      <Progress value={run.sites_finished} total={run.site_count} />
                      <p className="truncate text-xs text-muted-foreground">
                        {when.format(new Date(run.created_at))}
                        {run.created_by && ` · ${run.created_by}`} · {run.products.length} product
                        {run.products.length === 1 ? "" : "s"}
                        {run.checks_failed > 0 && ` · ${run.checks_failed} failed calls`}
                      </p>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
              No runs yet.
            </p>
          )
        ) : runs.error ? (
          <p role="alert" className="text-sm text-destructive">
            {runs.error.message}
          </p>
        ) : (
          <div className="grid gap-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}
      </div>
    </div>
  );
}
