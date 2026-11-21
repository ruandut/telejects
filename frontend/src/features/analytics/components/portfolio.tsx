/** Every project I can see at a glance: progress, overdue items, the week's flow and activity. */
import { Link } from "@tanstack/react-router";
import { AlertTriangle, CheckCircle2, FolderKanban, ListChecks } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { STATUS_COLOURS, STATUS_LABELS, type ProjectStatus } from "@/features/projects/types";
import { labelColour } from "@/lib/colours";

import { usePortfolio } from "../api";
import { WidgetChart } from "./widget-chart";

function Stat({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: typeof FolderKanban;
  tone?: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Icon className="size-4" style={tone ? { color: labelColour(tone) } : undefined} /> {label}
      </p>
      <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
        {value.toLocaleString("en-ZA")}
      </p>
    </div>
  );
}

function when(at: string) {
  return new Date(at).toLocaleString("en-ZA", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PortfolioView() {
  const portfolio = usePortfolio();
  if (!portfolio.data)
    return portfolio.error ? (
      <p className="text-sm text-destructive">{portfolio.error.message}</p>
    ) : (
      <Skeleton className="h-96" />
    );
  const { totals, projects, weeks, created, completed, recent } = portfolio.data;
  const flow = {
    labels: weeks,
    colours: [],
    series: [
      { key: "created", name: "Added", colour: null, data: created },
      { key: "completed", name: "Completed", colour: "green", data: completed },
    ],
    total: null,
    items: 0,
  };

  return (
    <div className="grid gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Projects" value={totals.projects} icon={FolderKanban} />
        <Stat label="Items" value={totals.items} icon={ListChecks} />
        <Stat label="Done" value={totals.done} icon={CheckCircle2} tone="green" />
        <Stat label="Overdue" value={totals.overdue} icon={AlertTriangle} tone="red" />
      </div>

      <section className="overflow-hidden rounded-xl border bg-card" aria-label="Projects">
        <div className="hidden grid-cols-[minmax(0,2fr)_7rem_minmax(0,2fr)_5rem_5rem_6rem] gap-4 border-b bg-muted/40 px-4 py-2 text-xs font-medium text-muted-foreground md:grid">
          <span>Project</span>
          <span>Status</span>
          <span>Progress</span>
          <span className="text-right">Items</span>
          <span className="text-right">Overdue</span>
          <span className="text-right">Next due</span>
        </div>
        {projects.map((p) => {
          const total = p.by_status.reduce((a, s) => a + s.count, 0);
          return (
            <Link
              key={p.id}
              to="/projects/$projectId"
              params={{ projectId: String(p.id) }}
              className="grid gap-2 border-b px-4 py-3 last:border-b-0 hover:bg-muted/40 md:grid-cols-[minmax(0,2fr)_7rem_minmax(0,2fr)_5rem_5rem_6rem] md:items-center md:gap-4"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className="size-3 shrink-0 rounded"
                  style={{ background: labelColour(p.colour) }}
                />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{p.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {[p.client, p.owner_name].filter(Boolean).join(" · ")}
                  </span>
                </span>
              </span>
              <span>
                <span
                  className="rounded-full px-2 py-0.5 text-xs text-white"
                  style={{ background: labelColour(STATUS_COLOURS[p.status as ProjectStatus]) }}
                >
                  {STATUS_LABELS[p.status as ProjectStatus]}
                </span>
              </span>
              <span className="grid gap-1">
                <span
                  className="flex h-2.5 overflow-hidden rounded-full bg-muted"
                  title={p.by_status.map((s) => `${s.label}: ${s.count}`).join(", ")}
                >
                  {p.by_status.map((s) => (
                    <span
                      key={s.label}
                      style={{ flexGrow: s.count, background: labelColour(s.colour) }}
                      className="border-r-2 border-card last:border-r-0"
                    />
                  ))}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {p.progress}% done · {p.done} of {total}
                </span>
              </span>
              <span className="text-sm tabular-nums md:text-right">{p.items}</span>
              <span
                className={`text-sm tabular-nums md:text-right ${p.overdue ? "font-medium text-destructive" : "text-muted-foreground"}`}
              >
                {p.overdue}
              </span>
              <span className="text-sm text-muted-foreground tabular-nums md:text-right">
                {p.next_due
                  ? new Date(`${p.next_due}T00:00:00`).toLocaleDateString("en-ZA", {
                      day: "numeric",
                      month: "short",
                    })
                  : "–"}
              </span>
            </Link>
          );
        })}
        {!projects.length && (
          <p className="p-6 text-center text-sm text-muted-foreground">
            No projects you can see yet.
          </p>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="min-w-0 rounded-xl border bg-card p-4" aria-label="Items per week">
          <h2 className="mb-2 font-medium">Added and completed, per week</h2>
          <WidgetChart kind="bar" data={flow} height={240} />
        </section>
        <section className="min-w-0 rounded-xl border bg-card p-4" aria-label="Latest activity">
          <h2 className="mb-2 font-medium">Latest activity</h2>
          <ul className="grid gap-2 text-sm">
            {recent.map((a) => (
              <li key={a.id} className="grid gap-0.5 border-b pb-2 last:border-b-0">
                <span className="line-clamp-2">
                  <span className="font-medium">{a.who}</span>{" "}
                  {a.kind === "value"
                    ? `changed ${a.column_title} on`
                    : a.kind === "created"
                      ? "added"
                      : a.kind === "update"
                        ? "wrote on"
                        : `${a.kind}`}{" "}
                  <Link
                    to="/projects/$projectId/boards/$boardId"
                    params={{ projectId: String(a.project), boardId: String(a.board) }}
                    search={{ item: a.item }}
                    className="font-medium text-primary hover:underline"
                  >
                    {a.item_name}
                  </Link>
                </span>
                {a.kind === "value" && (
                  <span className="truncate text-xs text-muted-foreground">
                    {a.old_text || "empty"} → {a.new_text || "empty"}
                  </span>
                )}
                <time className="text-xs text-muted-foreground" dateTime={a.at}>
                  {when(a.at)}
                </time>
              </li>
            ))}
            {!recent.length && <li className="text-muted-foreground">Nothing yet.</li>}
          </ul>
        </section>
      </div>
    </div>
  );
}
