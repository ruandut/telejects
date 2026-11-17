import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, Info } from "lucide-react";
import { useState } from "react";

import { NativeSelect } from "@/components/form";
import { NoAccess } from "@/components/no-access";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useConnections } from "@/features/integrations/api";
import { useLogLimits, useLogs } from "@/features/logs/api";
import { OUTCOMES, OutcomeBadge, shortUrl } from "@/features/logs/components/outcome";
import { NO_FILTERS, type LogFilters } from "@/features/logs/types";
import { usePermission } from "@/features/realms/permissions";

type Search = { run?: number };

export const Route = createFileRoute("/_app/logs/")({
  validateSearch: (search: Record<string, unknown>): Search => {
    const run = Number(search.run);
    return Number.isInteger(run) && run > 0 ? { run } : {};
  },
  component: LogsPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "medium" });

function LogsPage() {
  const me = useMe();
  const canView = usePermission("integrations.logs");
  if (me.data && !canView) return <NoAccess section="Logs" />;
  return <Logs />;
}

function Logs() {
  const { run } = Route.useSearch();
  const me = useMe();
  const [filters, setFilters] = useState<LogFilters>({
    ...NO_FILTERS,
    run: run ? String(run) : "",
  });
  const logs = useLogs(filters);
  const limits = useLogLimits();
  const seesConnections = usePermission("integrations.view");
  const connections = useConnections();
  const set = (changes: Partial<LogFilters>) => setFilters((f) => ({ ...f, page: 1, ...changes }));
  const pages = logs.data ? Math.max(1, Math.ceil(logs.data.count / logs.data.page_size)) : 1;

  return (
    <div className="mx-auto w-full max-w-6xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Logs</h1>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        Every request Telejects makes to your providers, and what they answered.
      </p>

      {limits.data && (
        <p className="mt-4 flex items-start gap-2 rounded-xl border bg-card p-3 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-primary" />
          <span>
            Telejects keeps the last{" "}
            <span className="font-medium tabular-nums">
              {limits.data.max_entries.toLocaleString("en-ZA")}
            </span>{" "}
            provider requests for {me.data?.realm?.name ?? "your company"}. Older ones are removed
            as new ones arrive, so a large run keeps only its latest requests here. Its results are
            kept with the run.
          </span>
        </p>
      )}

      <div className="mt-6 grid gap-2 sm:grid-cols-2 md:grid-cols-4 xl:grid-cols-[minmax(0,2fr)_repeat(4,minmax(0,1fr))]">
        <div className="sm:col-span-2 md:col-span-4 xl:col-span-1">
          <SearchInput
            label="Search logs"
            placeholder="Search URLs, requests, answers and errors"
            value={filters.search}
            onChange={(search) => set({ search })}
          />
        </div>
        <NativeSelect
          aria-label="Filter by connection"
          value={filters.connection}
          onChange={(e) => set({ connection: e.target.value })}
        >
          <option value="">All connections</option>
          {seesConnections &&
            connections.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by operation"
          value={filters.operation}
          onChange={(e) => set({ operation: e.target.value })}
        >
          <option value="">All operations</option>
          <option value="check_feasibility">Feasibility checks</option>
          <option value="sync_products">Product syncs</option>
          <option value="test_connection">Connection tests</option>
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by outcome"
          value={filters.outcome}
          onChange={(e) => set({ outcome: e.target.value })}
        >
          <option value="">Any outcome</option>
          <option value="error">Any error</option>
          {OUTCOMES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by HTTP status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
        >
          <option value="">Any status</option>
          <option value="2xx">2xx</option>
          <option value="4xx">4xx</option>
          <option value="5xx">5xx</option>
          <option value="none">No answer</option>
        </NativeSelect>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">From</span>
          <Input
            type="date"
            className="w-auto"
            value={filters.from}
            onChange={(e) => set({ from: e.target.value })}
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted-foreground">To</span>
          <Input
            type="date"
            className="w-auto"
            value={filters.to}
            onChange={(e) => set({ to: e.target.value })}
          />
        </label>
        {filters.run && (
          <Button variant="outline" size="sm" onClick={() => set({ run: "" })}>
            Run {filters.run} ✕
          </Button>
        )}
        {JSON.stringify({ ...filters, page: 1 }) !== JSON.stringify(NO_FILTERS) && (
          <Button variant="ghost" size="sm" onClick={() => setFilters(NO_FILTERS)}>
            Clear filters
          </Button>
        )}
      </div>

      <div className="mt-4">
        {logs.data ? (
          logs.data.results.length ? (
            <ul className="divide-y rounded-xl border bg-card">
              {logs.data.results.map((entry) => (
                <li key={entry.id}>
                  <Link
                    to="/logs/$logId"
                    params={{ logId: String(entry.id) }}
                    className="flex items-center gap-3 px-4 py-3 outline-none hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    <div className="grid min-w-0 flex-1 gap-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <OutcomeBadge outcome={entry.outcome} status={entry.status_code} />
                        <span className="font-medium">
                          {entry.connection_name || "Removed connection"}
                        </span>
                        <span className="text-muted-foreground">{entry.operation_label}</span>
                        {entry.attempt > 1 && (
                          <span className="text-xs text-muted-foreground">
                            attempt {entry.attempt}
                          </span>
                        )}
                      </div>
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {entry.method} {shortUrl(entry.url)}
                      </p>
                    </div>
                    <div className="hidden shrink-0 text-right text-xs text-muted-foreground tabular-nums sm:block">
                      <div>{when.format(new Date(entry.created_at))}</div>
                      {entry.duration_ms !== null && (
                        <div>{entry.duration_ms.toLocaleString("en-ZA")} ms</div>
                      )}
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
              No requests match.
            </p>
          )
        ) : logs.error ? (
          <p role="alert" className="text-sm text-destructive">
            {logs.error.message}
          </p>
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </div>

      {pages > 1 && (
        <div className="mt-4 flex items-center justify-between gap-2 text-sm">
          <Button
            variant="outline"
            disabled={filters.page <= 1}
            onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
          >
            Newer
          </Button>
          <span className="text-muted-foreground tabular-nums">
            Page {filters.page} of {pages}
          </span>
          <Button
            variant="outline"
            disabled={filters.page >= pages}
            onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
          >
            Older
          </Button>
        </div>
      )}
    </div>
  );
}
