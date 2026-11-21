/** Filters, sorting and hidden columns for the current view. */
import { ArrowDownUp, EyeOff, ListFilter, Plus, X } from "lucide-react";

import { NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { useBoardCtx } from "../board-context";
import type { Column, Filter, ViewConfig } from "../types";
import { str, FILTER_OPS, labelsOf } from "../values";

function ValueInput({
  column,
  filter,
  onChange,
}: {
  column: Column | undefined;
  filter: Filter;
  onChange: (v: unknown) => void;
}) {
  const { peopleList } = useBoardCtx();
  if (!column) return null;
  if (column.type === "status" || column.type === "dropdown")
    return (
      <NativeSelect
        value={str(filter.value)}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Value"
      >
        <option value="">Choose</option>
        {labelsOf(column).map((l) => (
          <option key={l.id} value={l.id}>
            {l.label}
          </option>
        ))}
      </NativeSelect>
    );
  if (column.type === "people")
    return (
      <NativeSelect
        value={str(filter.value)}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label="Person"
      >
        <option value="">Choose</option>
        {peopleList.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </NativeSelect>
    );
  if (column.type === "checkbox")
    return (
      <NativeSelect
        value={str(filter.value) || "true"}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Value"
      >
        <option value="true">Checked</option>
        <option value="false">Unchecked</option>
      </NativeSelect>
    );
  return (
    <Input
      type={column.type === "date" ? "date" : "text"}
      value={str(filter.value)}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Value"
    />
  );
}

export function FilterBar({
  config,
  onChange,
}: {
  config: ViewConfig;
  onChange: (config: ViewConfig) => void;
}) {
  const { board } = useBoardCtx();
  const filters = config.filters ?? [];
  const sort = config.sort ?? [];
  const hidden = new Set(config.hidden ?? []);
  const setFilter = (i: number, patch: Partial<Filter>) =>
    onChange({ ...config, filters: filters.map((f, n) => (n === i ? { ...f, ...patch } : f)) });
  const columns = board.columns;

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant={filters.length ? "secondary" : "ghost"} size="sm">
            <ListFilter /> Filter{filters.length ? ` (${filters.length})` : ""}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[min(36rem,calc(100vw-2rem))]">
          <p className="text-xs font-medium text-muted-foreground">
            Show items where all of these hold
          </p>
          {filters.map((filter, i) => {
            const column = columns.find((c) => c.key === filter.column);
            const op = FILTER_OPS.find((o) => o.op === filter.op);
            return (
              <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-1.5">
                <NativeSelect
                  aria-label="Column"
                  value={filter.column}
                  onChange={(e) => setFilter(i, { column: e.target.value, value: "" })}
                >
                  {columns.map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.title}
                    </option>
                  ))}
                </NativeSelect>
                <NativeSelect
                  aria-label="Comparison"
                  value={filter.op}
                  onChange={(e) => setFilter(i, { op: e.target.value })}
                >
                  {FILTER_OPS.map((o) => (
                    <option key={o.op} value={o.op}>
                      {o.label}
                    </option>
                  ))}
                </NativeSelect>
                {op?.needsValue ? (
                  <ValueInput
                    column={column}
                    filter={filter}
                    onChange={(value) => setFilter(i, { value })}
                  />
                ) : (
                  <span />
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove filter"
                  onClick={() =>
                    onChange({ ...config, filters: filters.filter((_, n) => n !== i) })
                  }
                >
                  <X />
                </Button>
              </div>
            );
          })}
          <div className="flex justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                onChange({
                  ...config,
                  filters: [...filters, { column: columns[0]?.key ?? "", op: "is", value: "" }],
                })
              }
            >
              <Plus /> Add filter
            </Button>
            {filters.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onChange({ ...config, filters: [] })}
              >
                Clear all
              </Button>
            )}
          </div>
        </PopoverContent>
      </Popover>

      <Popover>
        <PopoverTrigger asChild>
          <Button variant={sort.length ? "secondary" : "ghost"} size="sm">
            <ArrowDownUp /> Sort
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80">
          {sort.map((s, i) => (
            <div key={i} className="grid grid-cols-[1fr_auto_auto] gap-1.5">
              <NativeSelect
                aria-label="Sort by"
                value={s.column}
                onChange={(e) =>
                  onChange({
                    ...config,
                    sort: sort.map((x, n) => (n === i ? { ...x, column: e.target.value } : x)),
                  })
                }
              >
                <option value="name">Item name</option>
                {columns.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.title}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Direction"
                value={s.dir}
                onChange={(e) =>
                  onChange({
                    ...config,
                    sort: sort.map((x, n) =>
                      n === i ? { ...x, dir: e.target.value as "asc" | "desc" } : x,
                    ),
                  })
                }
              >
                <option value="asc">Ascending</option>
                <option value="desc">Descending</option>
              </NativeSelect>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove sort"
                onClick={() => onChange({ ...config, sort: sort.filter((_, n) => n !== i) })}
              >
                <X />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            className="justify-self-start"
            onClick={() => onChange({ ...config, sort: [...sort, { column: "name", dir: "asc" }] })}
          >
            <Plus /> Add sort
          </Button>
        </PopoverContent>
      </Popover>

      <Popover>
        <PopoverTrigger asChild>
          <Button variant={hidden.size ? "secondary" : "ghost"} size="sm">
            <EyeOff /> Hide{hidden.size ? ` (${hidden.size})` : ""}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64">
          <div className="grid max-h-72 gap-0.5 overflow-y-auto">
            {columns.map((c) => (
              <label
                key={c.key}
                className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-muted"
              >
                <Checkbox
                  checked={!hidden.has(c.key)}
                  onCheckedChange={(shown) => {
                    const next = new Set(hidden);
                    if (shown) next.delete(c.key);
                    else next.add(c.key);
                    onChange({ ...config, hidden: [...next] });
                  }}
                />
                <span className="truncate">{c.title}</span>
              </label>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}
