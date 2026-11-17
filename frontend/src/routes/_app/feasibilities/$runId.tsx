import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, Download, RotateCcw, Square } from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { NoAccess } from "@/components/no-access";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import {
  useExportRun,
  useRun,
  useRunAction,
  useRunLive,
  useRunSites,
} from "@/features/feasibilities/api";
import { SiteResults } from "@/features/feasibilities/components/site-results";
import { Progress, RunStatusBadge } from "@/features/feasibilities/components/status";
import type { Run } from "@/features/feasibilities/types";
import { usePermission } from "@/features/realms/permissions";
import { ApiError } from "@/network/errors";

export const Route = createFileRoute("/_app/feasibilities/$runId")({
  component: RunPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short" });

function RunPage() {
  const me = useMe();
  const canView = usePermission("feasibilities.view");
  const id = Number(Route.useParams().runId);
  if (me.data && !canView) return <NoAccess section="Feasibilities" />;
  return <RunDetail id={id} />;
}

function RunDetail({ id }: { id: number }) {
  useRunLive(id);
  const run = useRun(id);
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 p-4 md:p-8">
      <Link
        to="/feasibilities"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Feasibilities
      </Link>
      {run.data ? (
        <Loaded run={run.data} />
      ) : run.error ? (
        <p role="alert" className="text-sm text-destructive">
          {run.error instanceof ApiError && run.error.status === 404
            ? "There's no such run."
            : run.error.message}
        </p>
      ) : (
        <Skeleton className="h-40 w-full" />
      )}
    </div>
  );
}

function Loaded({ run }: { run: Run }) {
  const canRun = usePermission("feasibilities.run");
  const action = useRunAction(run.id);
  const exportRun = useExportRun(run.id);
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const sites = useRunSites(run.id, { page, state, search: search.trim() });
  const going = run.status === "queued" || run.status === "running";
  const pages = sites.data ? Math.max(1, Math.ceil(sites.data.count / sites.data.page_size)) : 1;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{run.name}</h1>
            <RunStatusBadge status={run.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Started {when.format(new Date(run.created_at))}
            {run.created_by && ` by ${run.created_by}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRun && going && (
            <Button
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate("cancel")}
            >
              <Square /> Cancel
            </Button>
          )}
          {canRun && run.status === "completed" && run.checks_failed > 0 && (
            <Button
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate("retry-failed")}
            >
              <RotateCcw /> Retry failed
            </Button>
          )}
          <Button
            variant="outline"
            disabled={exportRun.isPending}
            onClick={() => exportRun.mutate()}
          >
            <Download /> Export CSV
          </Button>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))] sm:items-center">
        <div className="grid gap-1">
          <span className="text-xs text-muted-foreground">Sites finished</span>
          <Progress value={run.sites_finished} total={run.site_count} />
        </div>
        <Figure
          label="Provider calls"
          value={`${run.checks_done + run.checks_failed} / ${run.checks_total}`}
        />
        <Figure
          label="Failed calls"
          value={String(run.checks_failed)}
          danger={run.checks_failed > 0}
        />
        <Figure label="Products" value={String(run.products.length)} />
      </div>

      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <SearchInput
          label="Search sites"
          placeholder="Search by site name"
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
        />
        <NativeSelect
          aria-label="Filter by state"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All sites</option>
          <option value="done">Answered</option>
          <option value="pending">Pending</option>
          <option value="error">With errors</option>
        </NativeSelect>
      </div>

      {sites.data ? (
        <SiteResults sites={sites.data.results} products={run.products} />
      ) : (
        <Skeleton className="h-40 w-full" />
      )}

      {pages > 1 && (
        <div className="flex items-center justify-between gap-2 text-sm">
          <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-muted-foreground tabular-nums">
            Page {page} of {pages}
          </span>
          <Button variant="outline" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </>
  );
}

function Figure({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="grid gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={`text-lg font-semibold tabular-nums ${danger ? "text-destructive" : ""}`}>
        {value}
      </span>
    </div>
  );
}
