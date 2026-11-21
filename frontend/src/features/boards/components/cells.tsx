/**
 * A cell of the board: how each column type shows its value and how it is edited. Every edit
 * goes out as that one cell (`onChange`), so people editing other cells never collide.
 */
import { Check, ExternalLink, MapPin, Plus, Star, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useItemSearch } from "@/features/boards/api";
import { labelColour } from "@/lib/colours";
import { cn } from "@/lib/utils";

import { useBoardCtx } from "../board-context";
import type { Column, Item, Linked } from "../types";
import { findLabel, formatDate, formatNumber, isBlank, labelsOf, str, textOf } from "../values";
import { Avatar, AvatarStack } from "./avatar";

type CellProps = {
  column: Column;
  item: Item;
  onChange: (value: unknown) => void;
  /** In the item drawer: roomier, always shows its editor's affordances. */
  wide?: boolean;
};

export function Cell(props: CellProps) {
  const { column } = props;
  const { canEdit } = useBoardCtx();
  const editable =
    canEdit && !["formula", "mirror", "item_id", "created", "updated"].includes(column.type);
  const Kind = EDITORS[column.type] ?? TextCell;
  if (!editable) return <ReadOnly {...props} />;
  return <Kind {...props} />;
}

function Shell({
  children,
  className,
  onClick,
}: {
  children?: ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-9 w-full min-w-0 items-center px-2 text-sm",
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

function ReadOnly({ column, item, wide }: CellProps) {
  const { people } = useBoardCtx();
  const value = item.values[column.key];
  if (column.type === "status") return <StatusChip column={column} value={value} />;
  if (column.type === "people") return <PeopleView ids={(value as number[]) ?? []} />;
  if (column.type === "mirror") return <MirrorView value={value as Linked | undefined} />;
  if (column.type === "connect") return <LinkedView value={value as Linked | undefined} />;
  if (column.type === "checkbox")
    return (
      <Shell className="justify-center">
        {value ? <Check className="size-4 text-label-green" /> : null}
      </Shell>
    );
  if (column.type === "rating") return <RatingView column={column} value={Number(value ?? 0)} />;
  if (column.type === "created") {
    const v = value as { at?: string; by?: string } | undefined;
    return (
      <Shell className="gap-1.5 text-muted-foreground">
        {v?.by && <Avatar id={v.by.length} name={v.by} className="size-5" />}
        <span className="truncate tabular-nums">{formatDate(v?.at)}</span>
      </Shell>
    );
  }
  const text = textOf(column, value, people);
  const numeric = ["number", "formula", "item_id"].includes(column.type);
  return (
    <Shell
      className={cn(
        numeric && !wide && "justify-end tabular-nums",
        !text && "text-muted-foreground",
      )}
    >
      <span className={cn("min-w-0", wide ? "whitespace-pre-wrap" : "truncate")}>{text}</span>
    </Shell>
  );
}

// --- text-like ---------------------------------------------------------------------------------

function InlineInput({
  initial,
  type = "text",
  onDone,
  onCancel,
  align,
}: {
  initial: string;
  type?: string;
  onDone: (value: string) => void;
  onCancel: () => void;
  align?: "right";
}) {
  const [text, setText] = useState(initial);
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);
  const key = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") onDone(text);
    if (event.key === "Escape") onCancel();
  };
  return (
    <input
      ref={ref}
      type={type}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={key}
      onBlur={() => onDone(text)}
      className={cn(
        "h-full min-h-9 w-full min-w-0 bg-background px-2 text-sm outline-none ring-2 ring-ring ring-inset",
        align === "right" && "text-right tabular-nums",
      )}
    />
  );
}

function useEditing(item: Item, column: Column) {
  const { focus } = useBoardCtx();
  const [editing, setEditing] = useState(false);
  const start = () => {
    setEditing(true);
    focus(item.id, column.key);
  };
  const stop = () => {
    setEditing(false);
    focus(null, null);
  };
  return { editing, start, stop };
}

function TextCell({ column, item, onChange, wide }: CellProps) {
  const { editing, start, stop } = useEditing(item, column);
  const value = item.values[column.key];
  const raw =
    column.type === "link"
      ? ((value as { url?: string })?.url ?? "")
      : value === undefined || value === null
        ? ""
        : str(value);
  const numeric = column.type === "number";
  if (editing)
    return (
      <InlineInput
        initial={raw}
        type={
          numeric
            ? "text"
            : column.type === "email"
              ? "email"
              : column.type === "phone"
                ? "tel"
                : "text"
        }
        align={numeric && !wide ? "right" : undefined}
        onCancel={stop}
        onDone={(text) => {
          stop();
          if (text.trim() !== raw) onChange(text.trim() || null);
        }}
      />
    );
  const shown = numeric
    ? formatNumber(value, column)
    : column.type === "link"
      ? (value as { text?: string; url?: string })?.text || raw
      : raw;
  return (
    <Shell
      onClick={start}
      className={cn("group/cell gap-1", numeric && !wide && "justify-end tabular-nums")}
    >
      <span className="min-w-0 truncate">{shown}</span>
      {column.type === "link" && raw && (
        <a
          href={raw}
          target="_blank"
          rel="noreferrer noopener"
          onClick={(e) => e.stopPropagation()}
          className="shrink-0 text-muted-foreground hover:text-foreground"
          aria-label="Open link"
        >
          <ExternalLink className="size-3.5" />
        </a>
      )}
      {column.type === "email" && raw && (
        <a href={`mailto:${raw}`} onClick={(e) => e.stopPropagation()} className="sr-only">
          Email
        </a>
      )}
    </Shell>
  );
}

function LongTextCell({ column, item, onChange, wide }: CellProps) {
  const value = (item.values[column.key] as string) ?? "";
  const [text, setText] = useState(value);
  const { focus } = useBoardCtx();
  return (
    <Popover
      onOpenChange={(open) => {
        if (open) {
          setText(value);
          focus(item.id, column.key);
        } else {
          focus(null, null);
          if (text !== value) onChange(text || null);
        }
      }}
    >
      <PopoverTrigger asChild>
        <button type="button" className="h-full w-full min-w-0 text-left">
          <Shell className={cn(!value && "text-muted-foreground")}>
            <span className={cn("min-w-0", wide ? "line-clamp-4 whitespace-pre-wrap" : "truncate")}>
              {value}
            </span>
          </Shell>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          autoFocus
          aria-label={column.title}
        />
        <p className="text-xs text-muted-foreground">Saved when you close this.</p>
      </PopoverContent>
    </Popover>
  );
}

// --- labels ------------------------------------------------------------------------------------

export function StatusChip({
  column,
  value,
  className,
}: {
  column: Column;
  value: unknown;
  className?: string;
}) {
  const label = findLabel(column, value);
  return (
    <div
      className={cn(
        "flex h-full min-h-9 w-full items-center justify-center px-2 text-center text-xs font-medium text-white",
        !label && "bg-muted/60",
        className,
      )}
      style={label ? { background: labelColour(label.colour) } : undefined}
    >
      <span className="truncate">{label?.label ?? ""}</span>
    </div>
  );
}

function StatusCell({ column, item, onChange }: CellProps) {
  const [open, setOpen] = useState(false);
  const { focus } = useBoardCtx();
  const value = item.values[column.key];
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        focus(next ? item.id : null, next ? column.key : null);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="h-full w-full"
          aria-label={`${column.title}: ${findLabel(column, value)?.label ?? "none"}`}
        >
          <StatusChip
            column={column}
            value={value}
            className="transition-opacity hover:opacity-90"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 gap-1.5 p-2">
        {labelsOf(column).map((label) => (
          <button
            key={label.id}
            type="button"
            className="flex h-8 items-center justify-center rounded-md px-2 text-xs font-medium text-white outline-none hover:opacity-90 focus-visible:ring-3 focus-visible:ring-ring/50"
            style={{ background: labelColour(label.colour) }}
            onClick={() => {
              setOpen(false);
              focus(null, null);
              if (label.id !== value) onChange(label.id);
            }}
          >
            {label.label}
          </button>
        ))}
        {value !== undefined && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setOpen(false);
              onChange(null);
            }}
          >
            Clear
          </Button>
        )}
      </PopoverContent>
    </Popover>
  );
}

function DropdownCell({ column, item, onChange }: CellProps) {
  const value = (item.values[column.key] as string[]) ?? [];
  const { focus } = useBoardCtx();
  const toggle = (id: string) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  return (
    <Popover onOpenChange={(open) => focus(open ? item.id : null, open ? column.key : null)}>
      <PopoverTrigger asChild>
        <button type="button" className="h-full w-full min-w-0">
          <Shell className="gap-1 overflow-hidden">
            {value.map((id) => {
              const label = findLabel(column, id);
              return label ? (
                <span
                  key={id}
                  className="shrink-0 truncate rounded-full border px-2 py-0.5 text-xs"
                >
                  {label.label}
                </span>
              ) : null;
            })}
          </Shell>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 gap-1 p-2">
        {labelsOf(column).length === 0 && (
          <p className="p-2 text-xs text-muted-foreground">
            No options yet: add them from the column's menu.
          </p>
        )}
        {labelsOf(column).map((label) => (
          <label
            key={label.id}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
          >
            <Checkbox checked={value.includes(label.id)} onCheckedChange={() => toggle(label.id)} />
            <span className="truncate">{label.label}</span>
          </label>
        ))}
      </PopoverContent>
    </Popover>
  );
}

// --- dates ---------------------------------------------------------------------------------------

function overdue(value: unknown, item: Item): boolean {
  if (typeof value !== "string" || item.done) return false;
  return value < new Date().toISOString().slice(0, 10);
}

function DateCell({ column, item, onChange }: CellProps) {
  const { editing, start, stop } = useEditing(item, column);
  const { board } = useBoardCtx();
  const value = item.values[column.key] as string | undefined;
  if (editing)
    return (
      <InlineInput
        initial={value ?? ""}
        type="date"
        onCancel={stop}
        onDone={(text) => {
          stop();
          if ((text || undefined) !== value) onChange(text || null);
        }}
      />
    );
  const late = board.due_column === column.key && overdue(value, item);
  return (
    <Shell
      onClick={start}
      className={cn("justify-center tabular-nums", late && "font-medium text-destructive")}
    >
      {formatDate(value)}
    </Shell>
  );
}

function TimelineCell({ column, item, onChange }: CellProps) {
  const value = item.values[column.key] as { start: string; end: string } | undefined;
  const [start, setStart] = useState(value?.start ?? "");
  const [end, setEnd] = useState(value?.end ?? "");
  const { focus } = useBoardCtx();
  return (
    <Popover
      onOpenChange={(open) => {
        focus(open ? item.id : null, open ? column.key : null);
        if (open) {
          setStart(value?.start ?? "");
          setEnd(value?.end ?? "");
        }
      }}
    >
      <PopoverTrigger asChild>
        <button type="button" className="h-full w-full">
          <Shell className="justify-center">
            {value ? (
              <span className="truncate rounded-full bg-label-blue px-2 py-0.5 text-xs text-white tabular-nums">
                {formatDate(value.start)} – {formatDate(value.end)}
              </span>
            ) : null}
          </Shell>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <div className="grid grid-cols-2 gap-2">
          <Input
            type="date"
            aria-label="Start"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <Input
            type="date"
            aria-label="End"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <div className="flex justify-between">
          <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
            Clear
          </Button>
          <Button size="sm" disabled={!start || !end} onClick={() => onChange({ start, end })}>
            Save
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// --- people ---------------------------------------------------------------------------------------

function PeopleView({ ids }: { ids: number[] }) {
  const { people } = useBoardCtx();
  return (
    <Shell className="justify-center">
      <AvatarStack people={ids.map((id) => ({ id, name: people.get(id)?.name ?? "Someone" }))} />
    </Shell>
  );
}

function PeopleCell({ column, item, onChange }: CellProps) {
  const { peopleList, focus } = useBoardCtx();
  const value = (item.values[column.key] as number[]) ?? [];
  const [search, setSearch] = useState("");
  const toggle = (id: number) =>
    onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id]);
  const shown = peopleList.filter((p) =>
    `${p.name} ${p.email}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <Popover onOpenChange={(open) => focus(open ? item.id : null, open ? column.key : null)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="h-full w-full"
          aria-label={`${column.title}: ${value.length} people`}
        >
          {value.length ? (
            <PeopleView ids={value} />
          ) : (
            <Shell className="justify-center text-muted-foreground/60">
              <Plus className="size-4" />
            </Shell>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2">
        <Input
          placeholder="Search people"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <div className="grid max-h-64 gap-0.5 overflow-y-auto">
          {shown.map((p) => (
            <label
              key={p.id}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted"
            >
              <Checkbox checked={value.includes(p.id)} onCheckedChange={() => toggle(p.id)} />
              <Avatar id={p.id} name={p.name} />
              <span className="min-w-0 truncate">{p.name}</span>
            </label>
          ))}
          {!shown.length && (
            <p className="p-2 text-xs text-muted-foreground">
              Nobody with access to this project matches.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// --- small ones -----------------------------------------------------------------------------------

function CheckboxCell({ column, item, onChange }: CellProps) {
  const value = !!item.values[column.key];
  return (
    <Shell className="justify-center">
      <Checkbox
        checked={value}
        aria-label={column.title}
        onCheckedChange={(next) => onChange(next ? true : null)}
      />
    </Shell>
  );
}

function RatingView({
  column,
  value,
  onPick,
}: {
  column: Column;
  value: number;
  onPick?: (n: number) => void;
}) {
  const max = column.settings.max ?? 5;
  return (
    <Shell className="justify-center gap-0.5">
      {Array.from({ length: max }, (_, i) => (
        <button
          key={i}
          type="button"
          disabled={!onPick}
          aria-label={`${i + 1} of ${max}`}
          onClick={() => onPick?.(value === i + 1 ? 0 : i + 1)}
          className="text-label-amber disabled:cursor-default"
        >
          <Star className={cn("size-3.5", i < value ? "fill-current" : "opacity-30")} />
        </button>
      ))}
    </Shell>
  );
}

function RatingCell({ column, item, onChange }: CellProps) {
  return (
    <RatingView
      column={column}
      value={Number(item.values[column.key] ?? 0)}
      onPick={(n) => onChange(n || null)}
    />
  );
}

function LocationCell({ column, item, onChange }: CellProps) {
  const value = item.values[column.key] as
    | { lat?: number; lng?: number; address?: string }
    | undefined;
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [address, setAddress] = useState("");
  const { focus } = useBoardCtx();
  const maps =
    value?.lat !== undefined ? `https://www.google.com/maps?q=${value.lat},${value.lng}` : null;
  return (
    <Popover
      onOpenChange={(open) => {
        focus(open ? item.id : null, open ? column.key : null);
        if (open) {
          setLat(value?.lat?.toString() ?? "");
          setLng(value?.lng?.toString() ?? "");
          setAddress(value?.address ?? "");
        }
      }}
    >
      <PopoverTrigger asChild>
        <button type="button" className="h-full w-full min-w-0 text-left">
          <Shell className="gap-1.5">
            {value && <MapPin className="size-3.5 shrink-0 text-label-red" />}
            <span className="min-w-0 truncate tabular-nums">
              {value?.address || (value?.lat !== undefined ? `${value.lat}, ${value.lng}` : "")}
            </span>
          </Shell>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72">
        <Input placeholder="Address" value={address} onChange={(e) => setAddress(e.target.value)} />
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder="Latitude"
            inputMode="decimal"
            value={lat}
            onChange={(e) => setLat(e.target.value)}
          />
          <Input
            placeholder="Longitude"
            inputMode="decimal"
            value={lng}
            onChange={(e) => setLng(e.target.value)}
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          {maps ? (
            <a
              href={maps}
              target="_blank"
              rel="noreferrer noopener"
              className="text-xs text-primary underline-offset-4 hover:underline"
            >
              Open in maps
            </a>
          ) : (
            <span />
          )}
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={() => onChange(null)}>
              Clear
            </Button>
            <Button
              size="sm"
              onClick={() => onChange({ address, lat: lat || undefined, lng: lng || undefined })}
            >
              Save
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function LinkedView({ value }: { value: Linked | undefined }) {
  const { openItem, board } = useBoardCtx();
  if (!value || isBlank(value)) return <Shell />;
  return (
    <Shell className="gap-1 overflow-hidden">
      {value.items.map((i) => (
        <span
          key={i.id}
          className="shrink-0 truncate rounded-md border bg-muted/50 px-1.5 py-0.5 text-xs"
          onClick={(e) => {
            if (i.board === board.id) {
              e.stopPropagation();
              openItem(i.id);
            }
          }}
        >
          {i.name}
        </span>
      ))}
      {value.hidden > 0 && (
        <span className="shrink-0 text-xs text-muted-foreground">{value.hidden} hidden</span>
      )}
    </Shell>
  );
}

function MirrorView({ value }: { value: Linked | undefined }) {
  if (!value || isBlank(value)) return <Shell />;
  return (
    <Shell className="gap-1 overflow-hidden">
      {value.items.map((i, n) =>
        i.colour ? (
          <span
            key={n}
            className="shrink-0 truncate rounded px-1.5 py-0.5 text-xs text-white"
            style={{ background: labelColour(i.colour) }}
          >
            {i.text}
          </span>
        ) : (
          <span key={n} className="shrink-0 truncate text-xs">
            {i.text}
          </span>
        ),
      )}
      {value.hidden > 0 && (
        <span className="shrink-0 text-xs text-muted-foreground">{value.hidden} hidden</span>
      )}
    </Shell>
  );
}

function ConnectCell({ column, item, onChange }: CellProps) {
  const value = item.values[column.key] as Linked | undefined;
  const ids = value?.items.map((i) => i.id) ?? [];
  const [search, setSearch] = useState("");
  const found = useItemSearch(column.settings.board, search);
  const { focus } = useBoardCtx();
  return (
    <Popover onOpenChange={(open) => focus(open ? item.id : null, open ? column.key : null)}>
      <PopoverTrigger asChild>
        <button type="button" className="h-full w-full min-w-0 text-left">
          {ids.length || value?.hidden ? (
            <LinkedView value={value} />
          ) : (
            <Shell className="justify-center text-muted-foreground/60">
              <Plus className="size-4" />
            </Shell>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-2">
        <div className="flex flex-wrap gap-1">
          {value?.items.map((i) => (
            <span
              key={i.id}
              className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs"
            >
              {i.name}
              <button
                type="button"
                aria-label={`Unlink ${i.name}`}
                onClick={() => onChange(ids.filter((x) => x !== i.id))}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
        <Input
          placeholder="Search items to link"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <div className="grid max-h-56 gap-0.5 overflow-y-auto">
          {found.data
            ?.filter((i) => !ids.includes(i.id))
            .map((i) => (
              <button
                key={i.id}
                type="button"
                className="truncate rounded-md px-2 py-1.5 text-left hover:bg-muted"
                onClick={() => onChange([...ids, i.id])}
              >
                {i.name}
              </button>
            ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

const EDITORS: Partial<Record<Column["type"], (props: CellProps) => ReactNode>> = {
  text: TextCell,
  number: TextCell,
  email: TextCell,
  phone: TextCell,
  link: TextCell,
  long_text: LongTextCell,
  status: StatusCell,
  dropdown: DropdownCell,
  date: DateCell,
  timeline: TimelineCell,
  people: PeopleCell,
  checkbox: CheckboxCell,
  rating: RatingCell,
  location: LocationCell,
  connect: ConnectCell,
};
