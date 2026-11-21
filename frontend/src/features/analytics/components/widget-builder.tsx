/** Build a chart: what to measure, how to group it, which boards, with a live preview. */
import {
  AreaChart,
  BarChart3,
  ChartColumnStacked,
  Hash,
  LineChart,
  PieChart,
  Plus,
  Table2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { str, FILTER_OPS } from "@/features/boards/values";
import { cn } from "@/lib/utils";

import { useDashboardActions, usePreview, useSources } from "../api";
import type { GroupBy, Widget, WidgetConfig, WidgetKind } from "../types";
import { WidgetChart } from "./widget-chart";

const KINDS: { kind: WidgetKind; label: string; icon: typeof BarChart3 }[] = [
  { kind: "bar", label: "Bar", icon: BarChart3 },
  { kind: "stacked", label: "Stacked", icon: ChartColumnStacked },
  { kind: "line", label: "Line", icon: LineChart },
  { kind: "area", label: "Area", icon: AreaChart },
  { kind: "pie", label: "Pie", icon: PieChart },
  { kind: "number", label: "Number", icon: Hash },
  { kind: "table", label: "Table", icon: Table2 },
];

const DATE_TYPES = ["date", "timeline", "created", "updated"];

function GroupPicker({
  value,
  onChange,
  titles,
  label,
  dated,
  allowNone = true,
}: {
  value: GroupBy | null | undefined;
  onChange: (g: GroupBy | null) => void;
  titles: { title: string; type: string }[];
  label: string;
  dated: boolean;
  allowNone?: boolean;
}) {
  const current = value ? (value.by === "column" ? `column:${value.column}` : value.by) : "";
  return (
    <Field label={label}>
      <NativeSelect
        value={current}
        onChange={(e) => {
          const v = e.target.value;
          if (!v) return onChange(null);
          if (v.startsWith("column:")) return onChange({ by: "column", column: v.slice(7) });
          onChange({ by: v as GroupBy["by"] });
        }}
      >
        {allowNone && (
          <option value="">
            {label === "Split into series by" ? "No split" : "Nothing (one total)"}
          </option>
        )}
        <optgroup label="Columns">
          {titles
            .filter(
              (t) =>
                !["long_text", "link", "location", "connect"].includes(t.type) &&
                (dated || !DATE_TYPES.includes(t.type)),
            )
            .map((t) => (
              <option key={t.title} value={`column:${t.title}`}>
                {t.title}
              </option>
            ))}
        </optgroup>
        <optgroup label="Other">
          <option value="group">Group</option>
          <option value="board">Board</option>
          <option value="project">Project</option>
          <option value="done">Done or not</option>
          {dated && <option value="created">Date created</option>}
          {dated && <option value="completed">Date completed</option>}
        </optgroup>
      </NativeSelect>
    </Field>
  );
}

export function WidgetBuilder({
  project,
  dashboard,
  widget,
  onClose,
}: {
  project: number | null;
  dashboard: number;
  widget: Widget | null;
  onClose: () => void;
}) {
  const sources = useSources(project);
  const actions = useDashboardActions(project);
  const [title, setTitle] = useState(widget?.title ?? "");
  const [kind, setKind] = useState<WidgetKind>(widget?.kind ?? "bar");
  const [width, setWidth] = useState(widget?.width ?? 1);
  const [config, setConfig] = useState<WidgetConfig>(
    widget?.config ?? {
      metric: { op: "count" },
      group_by: { by: "column", column: "Status" },
      bucket: "month",
    },
  );
  const preview = usePreview(project, config);

  const boards = useMemo(() => {
    const all = sources.data ?? [];
    return config.boards?.length ? all.filter((b) => config.boards!.includes(b.id)) : all;
  }, [sources.data, config.boards]);
  const titles = useMemo(() => {
    const seen = new Map<string, { title: string; type: string }>();
    for (const b of boards)
      for (const c of b.columns)
        if (!seen.has(c.title.toLowerCase()))
          seen.set(c.title.toLowerCase(), { title: c.title, type: c.type });
    return [...seen.values()];
  }, [boards]);
  const numeric = titles.filter((t) => ["number", "formula", "rating", "mirror"].includes(t.type));
  const groupColumn = titles.find((t) => t.title === config.group_by?.column);
  const dated =
    ["created", "completed"].includes(config.group_by?.by ?? "") ||
    (!!groupColumn && DATE_TYPES.includes(groupColumn.type));
  const filters = config.filters ?? [];

  const save = () =>
    actions.saveWidget.mutate(
      { id: widget?.id, dashboard, title: title || "Untitled chart", kind, config, width },
      { onSuccess: onClose },
    );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>{widget ? "Edit chart" : "Add a chart"}</DialogTitle>
          <DialogDescription>
            Counted live over the items you can see
            {project ? " in this project" : " in every project"}.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-6 md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <div className="grid content-start gap-4">
            <Field label="Title">
              <Input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Sites by status"
                autoFocus
              />
            </Field>
            <div className="grid gap-2">
              <span className="text-sm font-medium">Chart</span>
              <div className="grid grid-cols-4 gap-1.5">
                {KINDS.map(({ kind: k, label, icon: Icon }) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setKind(k)}
                    aria-pressed={kind === k}
                    className={cn(
                      "flex flex-col items-center gap-1 rounded-md border p-2 text-xs hover:bg-muted",
                      kind === k && "border-primary bg-accent",
                    )}
                  >
                    <Icon className="size-4" /> {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Measure">
                <NativeSelect
                  value={config.metric?.op ?? "count"}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      metric: {
                        op: e.target.value as "count",
                        column:
                          e.target.value === "count"
                            ? undefined
                            : (config.metric?.column ?? numeric[0]?.title),
                      },
                    })
                  }
                >
                  <option value="count">Count of items</option>
                  <option value="sum">Sum of</option>
                  <option value="avg">Average of</option>
                  <option value="min">Smallest</option>
                  <option value="max">Largest</option>
                </NativeSelect>
              </Field>
              {config.metric?.op !== "count" && (
                <Field label="Column">
                  <NativeSelect
                    value={config.metric?.column ?? ""}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        metric: { op: config.metric!.op, column: e.target.value },
                      })
                    }
                  >
                    {numeric.map((t) => (
                      <option key={t.title} value={t.title}>
                        {t.title}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
            </div>
            {kind !== "number" && (
              <GroupPicker
                label="Group by"
                titles={titles}
                dated
                value={config.group_by}
                onChange={(group_by) =>
                  setConfig({ ...config, group_by: group_by ?? { by: "none" } })
                }
              />
            )}
            {dated && kind !== "number" && (
              <Field label="Per">
                <NativeSelect
                  value={config.bucket ?? "month"}
                  onChange={(e) => setConfig({ ...config, bucket: e.target.value as "month" })}
                >
                  <option value="day">Day</option>
                  <option value="week">Week</option>
                  <option value="month">Month</option>
                  <option value="quarter">Quarter</option>
                  <option value="year">Year</option>
                </NativeSelect>
              </Field>
            )}
            {["bar", "stacked", "line", "area", "table"].includes(kind) && (
              <GroupPicker
                label="Split into series by"
                titles={titles}
                dated={false}
                value={config.series_by}
                onChange={(series_by) => setConfig({ ...config, series_by })}
              />
            )}
            <div className="grid gap-2">
              <span className="text-sm font-medium">Only items where</span>
              {filters.map((f, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-1">
                  <NativeSelect
                    aria-label="Column"
                    value={f.column}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        filters: filters.map((x, n) =>
                          n === i ? { ...x, column: e.target.value } : x,
                        ),
                      })
                    }
                  >
                    {titles.map((t) => (
                      <option key={t.title} value={t.title}>
                        {t.title}
                      </option>
                    ))}
                  </NativeSelect>
                  <NativeSelect
                    aria-label="Comparison"
                    value={f.op}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        filters: filters.map((x, n) =>
                          n === i ? { ...x, op: e.target.value } : x,
                        ),
                      })
                    }
                  >
                    {FILTER_OPS.map((o) => (
                      <option key={o.op} value={o.op}>
                        {o.label}
                      </option>
                    ))}
                  </NativeSelect>
                  <Input
                    aria-label="Value"
                    value={str(f.value)}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        filters: filters.map((x, n) =>
                          n === i ? { ...x, value: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Remove"
                    onClick={() =>
                      setConfig({ ...config, filters: filters.filter((_, n) => n !== i) })
                    }
                  >
                    <X />
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                size="sm"
                className="justify-self-start"
                onClick={() =>
                  setConfig({
                    ...config,
                    filters: [...filters, { column: titles[0]?.title ?? "", op: "is", value: "" }],
                  })
                }
              >
                <Plus /> Add a filter
              </Button>
            </div>
            <div className="grid gap-1.5">
              <span className="text-sm font-medium">Boards</span>
              <div className="grid max-h-36 gap-1 overflow-y-auto rounded-md border p-2">
                {sources.data?.map((b) => (
                  <label key={b.id} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={!config.boards?.length || config.boards.includes(b.id)}
                      onCheckedChange={(on) => {
                        const all = sources.data!.map((x) => x.id);
                        const current = config.boards?.length ? config.boards : all;
                        const next = on ? [...current, b.id] : current.filter((x) => x !== b.id);
                        setConfig({ ...config, boards: next.length === all.length ? [] : next });
                      }}
                    />
                    <span className="truncate">
                      {project ? b.name : `${b.project.name} · ${b.name}`}
                    </span>
                  </label>
                ))}
              </div>
            </div>
            <Field label="Width">
              <NativeSelect value={width} onChange={(e) => setWidth(Number(e.target.value))}>
                <option value={1}>A third</option>
                <option value={2}>Two thirds</option>
                <option value={3}>Full width</option>
              </NativeSelect>
            </Field>
          </div>
          <div className="min-w-0 rounded-xl border bg-card p-4">
            <p className="mb-3 font-medium">{title || "Preview"}</p>
            {preview.data ? (
              <WidgetChart kind={kind} data={preview.data} height={280} />
            ) : preview.error ? (
              <p className="text-sm text-destructive">{preview.error.message}</p>
            ) : (
              <Skeleton className="h-64" />
            )}
          </div>
        </div>
        <FormError error={actions.saveWidget.error} />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} disabled={actions.saveWidget.isPending}>
            {widget ? "Save chart" : "Add chart"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
