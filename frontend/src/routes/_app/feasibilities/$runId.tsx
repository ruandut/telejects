import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Square,
} from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { NameDialog } from "@/components/name-dialog";
import { NoAccess } from "@/components/no-access";
import { SearchInput } from "@/components/search-input";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import {
  useExportRun,
  useRenameRun,
  useRun,
  useRunAction,
  useRunLive,
  useRunSites,
} from "@/features/feasibilities/api";
import { SiteResults } from "@/features/feasibilities/components/site-results";
import { Progress, RunStatusBadge } from "@/features/feasibilities/components/status";
import type { Run, SitePage } from "@/features/feasibilities/types";
import { usePermission } from "@/features/realms/permissions";
import { ApiError } from "@/network/errors";
import {
  SITE_PAGE_SIZES,
  type SitePageSize,
  useFeasibilityFilters,
} from "@/stores/feasibility-filters";

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
  const seesLogs = usePermission("integrations.logs");
  const action = useRunAction(run.id);
  const exportRun = useExportRun(run.id);
  const rename = useRenameRun(run.id);
  const [renaming, setRenaming] = useState(false);
  const [state, setState] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = useFeasibilityFilters((s) => s.pageSize);
  const setPageSize = useFeasibilityFilters((s) => s.setPageSize);
  const sites = useRunSites(run.id, { page, pageSize, state, search: search.trim() });
  const going = run.status === "queued" || run.status === "running" || run.status === "paused";

  return (
    <>
      {renaming && (
        <NameDialog
          title="Rename run"
          initial={run.name}
          maxLength={100}
          pending={rename.isPending}
          onSubmit={(name) => rename.mutate(name, { onSuccess: () => setRenaming(false) })}
          onClose={() => setRenaming(false)}
        />
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{run.name}</h1>
            {canRun && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground"
                aria-label="Rename run"
                title="Rename"
                onClick={() => setRenaming(true)}
              >
                <Pencil />
              </Button>
            )}
            <RunStatusBadge status={run.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Started {when.format(new Date(run.created_at))}
            {run.created_by && ` by ${run.created_by}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRun && run.status === "running" && (
            <Button
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate("pause")}
            >
              <Pause /> Pause
            </Button>
          )}
          {canRun && run.status === "paused" && (
            <Button disabled={action.isPending} onClick={() => action.mutate("resume")}>
              <Play /> Continue
            </Button>
          )}
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
          {canRun && !going && (
            <ConfirmDialog
              title={`Run "${run.name}" again?`}
              description={`All ${run.site_count.toLocaleString("en-ZA")} sites are checked again, and the new results replace the ones this run has now.`}
              cancelLabel="Keep these results"
              confirmLabel={
                <>
                  <RefreshCw /> Run again
                </>
              }
              onConfirm={() => action.mutate("rerun")}
            >
              <Button variant="outline" disabled={action.isPending}>
                <RefreshCw /> Run again
              </Button>
            </ConfirmDialog>
          )}
          {seesLogs && (
            <Button variant="outline" asChild>
              <Link to="/logs" search={{ run: run.id }}>
                <ScrollText /> Requests
              </Link>
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

      {sites.data && sites.data.count > 0 && (
        <Pager
          data={sites.data}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size);
            setPage(1);
          }}
        />
      )}
    </>
  );
}

/** Rows per page, "21–40 of 312", and previous and next. The page shown is the server's: it
 * moves back to the last page when the list shrinks under it. */
function Pager({
  data,
  onPage,
  onPageSize,
}: {
  data: SitePage;
  onPage: (page: number) => void;
  onPageSize: (size: SitePageSize) => void;
}) {
  const first = (data.page - 1) * data.page_size + 1;
  const last = first + data.results.length - 1;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm">
      <label className="flex items-center gap-2 text-muted-foreground">
        Rows per page
        <NativeSelect
          className="w-20"
          value={data.page_size}
          onChange={(e) => onPageSize(Number(e.target.value) as SitePageSize)}
        >
          {SITE_PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </NativeSelect>
      </label>
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground tabular-nums" aria-live="polite">
          {first}–{last} of {data.count}
        </span>
        <Button
          variant="outline"
          size="icon"
          aria-label="Previous page"
          disabled={!data.previous}
          onClick={() => onPage(data.page - 1)}
        >
          <ChevronLeft />
        </Button>
        <Button
          variant="outline"
          size="icon"
          aria-label="Next page"
          disabled={!data.next}
          onClick={() => onPage(data.page + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
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
