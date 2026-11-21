/** A project's (or the company's) dashboards: tabs of chart widgets in a three-column grid. */
import { LayoutDashboard, MoreHorizontal, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { NameDialog } from "@/components/name-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

import { useDashboardActions, useDashboards, useWidgetData } from "../api";
import type { Widget } from "../types";
import { WidgetBuilder } from "./widget-builder";
import { WidgetChart } from "./widget-chart";

const SPAN = { 1: "lg:col-span-1", 2: "lg:col-span-2", 3: "lg:col-span-3" } as Record<
  number,
  string
>;

function WidgetCard({
  widget,
  canChange,
  onEdit,
  onRemove,
}: {
  widget: Widget;
  canChange: boolean;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const data = useWidgetData(widget.id, JSON.stringify([widget.kind, widget.config]));
  const [removing, setRemoving] = useState(false);
  return (
    <section
      className={cn(
        "min-w-0 rounded-xl border bg-card p-4",
        SPAN[widget.width] ?? "",
        widget.width > 1 && "md:col-span-2",
      )}
      aria-label={widget.title}
    >
      <header className="mb-2 flex items-start justify-between gap-2">
        <h3 className="font-medium">{widget.title}</h3>
        {canChange && (
          <DropdownMenu>
            <DropdownMenuTrigger
              className="rounded p-1 text-muted-foreground hover:bg-muted"
              aria-label={`${widget.title} options`}
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={onEdit}>
                <Pencil /> Edit
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onSelect={() => setRemoving(true)}>
                <Trash2 /> Remove
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <ConfirmDialog
          open={removing}
          onOpenChange={setRemoving}
          title={`Remove ${widget.title}?`}
          description="Only the chart goes. The boards' items are untouched."
          confirmLabel="Remove chart"
          destructive
          onConfirm={onRemove}
        />
      </header>
      {data.data ? (
        <WidgetChart kind={widget.kind} data={data.data} />
      ) : data.error ? (
        <p className="text-sm text-destructive">{data.error.message}</p>
      ) : (
        <Skeleton className="h-48" />
      )}
    </section>
  );
}

export function Dashboards({ project, canChange }: { project: number | null; canChange: boolean }) {
  const dashboards = useDashboards(project);
  const actions = useDashboardActions(project);
  const [active, setActive] = useState<number | null>(null);
  const [editing, setEditing] = useState<Widget | "new" | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [deletingDashboard, setDeletingDashboard] = useState(false);
  const list = dashboards.data ?? [];
  const current = list.find((d) => d.id === active) ?? list[0];

  if (dashboards.isLoading) return <Skeleton className="h-64" />;
  if (!list.length)
    return (
      <div className="rounded-xl border border-dashed p-8 text-center">
        <LayoutDashboard className="mx-auto size-8 text-muted-foreground" />
        <h2 className="mt-2 font-semibold">No dashboards yet</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Chart {project ? "this project's" : "every project's"} items: progress, money, dates,
          whatever your columns hold.
        </p>
        {canChange ? (
          <div className="mt-4 flex justify-center gap-2">
            <Button
              onClick={() =>
                actions.create.mutate(
                  { name: "Overview", starter: true },
                  { onSuccess: (d) => setActive(d.id) },
                )
              }
            >
              <Sparkles /> Start with suggested charts
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                actions.create.mutate({ name: "Dashboard" }, { onSuccess: (d) => setActive(d.id) })
              }
            >
              Blank dashboard
            </Button>
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">
            Ask someone who manages {project ? "this project" : "projects"} to add one.
          </p>
        )}
      </div>
    );

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Dashboards" className="flex min-w-0 gap-1 overflow-x-auto">
          {list.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => setActive(d.id)}
              aria-current={d.id === current?.id ? "page" : undefined}
              className={cn(
                "shrink-0 border-b-2 border-transparent px-2 py-1.5 text-sm",
                d.id === current?.id
                  ? "border-primary font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {d.name}
            </button>
          ))}
        </nav>
        {canChange && current && (
          <div className="ml-auto flex gap-1">
            <Button size="sm" onClick={() => setEditing("new")}>
              <Plus /> Add chart
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost" aria-label="Dashboard options">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() =>
                    actions.create.mutate(
                      { name: "Dashboard" },
                      { onSuccess: (d) => setActive(d.id) },
                    )
                  }
                >
                  <Plus /> New dashboard
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setRenaming(true)}>
                  <Pencil /> Rename
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setDeletingDashboard(true)}>
                  <Trash2 /> Delete dashboard
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
      {current && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {current.widgets.map((w) => (
            <WidgetCard
              key={w.id}
              widget={w}
              canChange={canChange}
              onEdit={() => setEditing(w)}
              onRemove={() => actions.removeWidget.mutate(w.id)}
            />
          ))}
          {!current.widgets.length && (
            <p className="text-sm text-muted-foreground">This dashboard is empty. Add a chart.</p>
          )}
        </div>
      )}
      {current && (
        <ConfirmDialog
          open={deletingDashboard}
          onOpenChange={setDeletingDashboard}
          title={`Delete ${current.name}?`}
          description="Its charts go with it. The boards' items are untouched."
          confirmLabel="Delete"
          destructive
          onConfirm={() => actions.remove.mutate(current.id)}
        />
      )}
      {renaming && current && (
        <NameDialog
          title="Rename dashboard"
          initial={current.name}
          pending={actions.rename.isPending}
          onClose={() => setRenaming(false)}
          onSubmit={(name) =>
            actions.rename.mutate({ id: current.id, name }, { onSuccess: () => setRenaming(false) })
          }
        />
      )}
      {editing && current && (
        <WidgetBuilder
          project={project}
          dashboard={current.id}
          widget={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}
