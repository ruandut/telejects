/**
 * The board as a table, monday.com style: one section per group, a sticky item name, a cell per
 * column, a summary under each group and a row to add items. Rows drag between groups. Coloured
 * rings show the cells other people are in right now.
 */
import {
  ChevronDown,
  ChevronRight,
  EyeOff,
  GripVertical,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Settings2,
  Trash2,
} from "lucide-react";
import { Fragment, useMemo, useState, type DragEvent } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useIsMobile } from "@/hooks/use-mobile";
import { LABEL_COLOURS, labelColour, personColour } from "@/lib/colours";
import { cn } from "@/lib/utils";

import { useColumnActions, useGroupActions, useItemActions, useUpdateBoard } from "../api";
import { useBoardCtx } from "../board-context";
import type { Column, Group, Item } from "../types";
import { str, findLabel, formatNumber, labelsOf } from "../values";
import { Avatar } from "./avatar";
import { Cell } from "./cells";
import { ColumnDialog } from "./column-dialog";

const SELECT_W = 36;
const NAME_W = 300;
const NAME_W_PHONE = 170;
const ADD_W = 48;

export function BoardTable({
  items,
  columns,
  groups,
  selected,
  onSelect,
  onHide,
}: {
  items: Item[];
  columns: Column[];
  groups: Group[];
  selected: Set<number>;
  onSelect: (ids: number[], on: boolean) => void;
  onHide: (key: string) => void;
}) {
  const { board, canManage } = useBoardCtx();
  const nameWidth = useIsMobile() ? NAME_W_PHONE : NAME_W;
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [dialog, setDialog] = useState<{ column: Column | null; after?: string | null } | null>(
    null,
  );
  const groupActions = useGroupActions(board.id);
  const template = `${SELECT_W}px ${nameWidth}px ${columns.map((c) => `${c.width}px`).join(" ")} ${ADD_W}px`;
  const width = SELECT_W + nameWidth + ADD_W + columns.reduce((sum, c) => sum + c.width, 0);
  const byGroup = useMemo(() => {
    const map = new Map<number, Item[]>(groups.map((g) => [g.id, []]));
    for (const item of items) map.get(item.group)?.push(item);
    return map;
  }, [items, groups]);

  return (
    <div className="overflow-x-auto overscroll-x-contain pb-4" role="table" aria-label={board.name}>
      <div style={{ minWidth: width }} className="grid gap-6">
        {groups.map((group) => (
          <GroupSection
            key={group.id}
            group={group}
            items={byGroup.get(group.id) ?? []}
            columns={columns}
            template={template}
            collapsed={collapsed.has(group.id)}
            onToggle={() =>
              setCollapsed((prev) => {
                const next = new Set(prev);
                if (next.has(group.id)) next.delete(group.id);
                else next.add(group.id);
                return next;
              })
            }
            selected={selected}
            onSelect={onSelect}
            onEditColumn={(column) => setDialog({ column })}
            onAddColumn={(after) => setDialog({ column: null, after })}
            onHide={onHide}
          />
        ))}
        {canManage && (
          <button
            type="button"
            className="sticky left-0 flex w-fit items-center gap-2 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
            onClick={() =>
              groupActions.create.mutate({
                name: "New group",
                colour: LABEL_COLOURS[(groups.length + 4) % LABEL_COLOURS.length],
              })
            }
          >
            <Plus className="size-4" /> Add group
          </button>
        )}
      </div>
      {dialog && (
        <ColumnDialog
          board={board}
          column={dialog.column}
          after={dialog.after}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

function GroupSection({
  group,
  items,
  columns,
  template,
  collapsed,
  onToggle,
  selected,
  onSelect,
  onEditColumn,
  onAddColumn,
  onHide,
}: {
  group: Group;
  items: Item[];
  columns: Column[];
  template: string;
  collapsed: boolean;
  onToggle: () => void;
  selected: Set<number>;
  onSelect: (ids: number[], on: boolean) => void;
  onEditColumn: (column: Column) => void;
  onAddColumn: (after: string | null) => void;
  onHide: (key: string) => void;
}) {
  const { board, canEdit, canManage } = useBoardCtx();
  const colour = labelColour(group.colour);
  const actions = useItemActions(board.id);
  const groupActions = useGroupActions(board.id);
  const [renaming, setRenaming] = useState(false);
  const [dropping, setDropping] = useState(false);
  const [deletingGroup, setDeletingGroup] = useState(false);
  const allSelected = items.length > 0 && items.every((i) => selected.has(i.id));

  const dropOnGroup = (event: DragEvent) => {
    event.preventDefault();
    setDropping(false);
    const id = Number(event.dataTransfer.getData("text/item"));
    if (id) actions.update.mutate({ id, group: group.id, after: items.at(-1)?.id ?? null });
  };

  return (
    <section
      aria-label={group.name}
      onDragOver={(e) => {
        if (canEdit && e.dataTransfer.types.includes("text/item")) {
          e.preventDefault();
          setDropping(true);
        }
      }}
      onDragLeave={() => setDropping(false)}
      onDrop={dropOnGroup}
      className={cn("rounded-lg", dropping && "ring-2 ring-ring/40")}
    >
      <div className="sticky left-0 mb-1 flex w-fit max-w-[calc(100vw-3rem)] items-center gap-1.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand group" : "Collapse group"}
          style={{ color: colour }}
        >
          {collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
        </button>
        {renaming ? (
          <input
            autoFocus
            defaultValue={group.name}
            className="rounded border bg-background px-1 text-base font-semibold outline-none"
            style={{ color: colour }}
            onBlur={(e) => {
              setRenaming(false);
              if (e.target.value.trim() && e.target.value !== group.name)
                groupActions.update.mutate({ id: group.id, name: e.target.value });
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setRenaming(false);
            }}
          />
        ) : (
          <h3
            className="truncate text-base font-semibold"
            style={{ color: colour }}
            onDoubleClick={() => canManage && setRenaming(true)}
          >
            {group.name}
          </h3>
        )}
        <span className="text-xs text-muted-foreground tabular-nums">
          {items.length} item{items.length === 1 ? "" : "s"}
        </span>
        {canManage && (
          <DropdownMenu>
            <DropdownMenuTrigger
              className="rounded p-0.5 text-muted-foreground hover:bg-muted"
              aria-label="Group options"
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onSelect={() => setRenaming(true)}>
                <Pencil /> Rename
              </DropdownMenuItem>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger>Colour</DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="grid grid-cols-6 gap-1 p-2">
                  {LABEL_COLOURS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      aria-label={c}
                      className="size-5 rounded-full"
                      style={{ background: labelColour(c) }}
                      onClick={() => groupActions.update.mutate({ id: group.id, colour: c })}
                    />
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onSelect={() => setDeletingGroup(true)}>
                <Trash2 /> Delete group
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <ConfirmDialog
        open={deletingGroup}
        onOpenChange={setDeletingGroup}
        title={`Delete ${group.name}?`}
        description={`Its ${items.length} item${items.length === 1 ? "" : "s"} are deleted with it. This can't be undone.`}
        confirmLabel="Delete group"
        destructive
        onConfirm={() => groupActions.remove.mutate(group.id)}
      />

      {!collapsed && (
        <div
          className="overflow-hidden rounded-lg border bg-card"
          style={{ borderLeft: `4px solid ${colour}` }}
        >
          <div
            role="row"
            className="grid border-b bg-muted/40 text-xs font-medium text-muted-foreground"
            style={{ gridTemplateColumns: template }}
          >
            <div className="sticky left-0 z-[2] flex items-center justify-center bg-muted">
              {canEdit && (
                <Checkbox
                  aria-label={`Select every item in ${group.name}`}
                  checked={allSelected}
                  onCheckedChange={(on) =>
                    onSelect(
                      items.map((i) => i.id),
                      !!on,
                    )
                  }
                />
              )}
            </div>
            <div
              role="columnheader"
              className="sticky z-[2] flex items-center border-r bg-muted px-2"
              style={{ left: SELECT_W }}
            >
              Item
            </div>
            {columns.map((column) => (
              <ColumnHeader
                key={column.key}
                column={column}
                onEdit={() => onEditColumn(column)}
                onHide={() => onHide(column.key)}
                onAddAfter={() => onAddColumn(column.key)}
              />
            ))}
            <div className="flex items-center justify-center">
              {canManage && (
                <button
                  type="button"
                  aria-label="Add a column"
                  className="rounded p-1 hover:bg-muted"
                  onClick={() => onAddColumn(null)}
                >
                  <Plus className="size-4" />
                </button>
              )}
            </div>
          </div>
          {items.map((item, index) => (
            <Row
              key={item.id}
              item={item}
              columns={columns}
              template={template}
              colour={colour}
              selected={selected.has(item.id)}
              onSelect={(on) => onSelect([item.id], on)}
              previous={items[index - 1]?.id ?? null}
            />
          ))}
          {canEdit && <AddItem group={group} template={template} />}
          <Summary items={items} columns={columns} template={template} />
        </div>
      )}
    </section>
  );
}

function ColumnHeader({
  column,
  onEdit,
  onHide,
  onAddAfter,
}: {
  column: Column;
  onEdit: () => void;
  onHide: () => void;
  onAddAfter: () => void;
}) {
  const { board, canManage } = useBoardCtx();
  const columns = useColumnActions(board.id);
  const updateBoard = useUpdateBoard(board.id);
  const [resizing, setResizing] = useState<number | null>(null);
  const [deletingColumn, setDeletingColumn] = useState(false);
  const isStatus = board.status_column === column.key;
  const isDue = board.due_column === column.key;
  return (
    <div
      role="columnheader"
      className="group/head relative flex min-w-0 items-center justify-center gap-1 border-r px-2 py-2"
      title={column.description || column.title}
    >
      <span className="truncate">{column.title}</span>
      {(isStatus || isDue) && (
        <span className="shrink-0 rounded bg-muted px-1 text-[10px]">
          {isStatus ? "progress" : "due"}
        </span>
      )}
      {canManage && (
        <DropdownMenu>
          <DropdownMenuTrigger
            className="absolute right-1 rounded p-0.5 opacity-0 group-hover/head:opacity-100 hover:bg-muted focus-visible:opacity-100"
            aria-label={`${column.title} options`}
          >
            <MoreHorizontal className="size-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuLabel className="text-xs">{column.title}</DropdownMenuLabel>
            <DropdownMenuItem onSelect={onEdit}>
              <Settings2 /> Settings
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onAddAfter}>
              <Plus /> Add a column to the right
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onHide}>
              <EyeOff /> Hide in this view
            </DropdownMenuItem>
            {column.type === "status" && !isStatus && (
              <DropdownMenuItem onSelect={() => updateBoard.mutate({ status_column: column.key })}>
                Use for the board's progress
              </DropdownMenuItem>
            )}
            {["date", "timeline"].includes(column.type) && !isDue && (
              <DropdownMenuItem onSelect={() => updateBoard.mutate({ due_column: column.key })}>
                Use as the due date
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setDeletingColumn(true)}>
              <Trash2 /> Delete column
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {canManage && (
        <span
          aria-hidden
          className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-ring/40"
          onPointerDown={(e) => {
            const startX = e.clientX;
            const start = column.width;
            const el = e.currentTarget;
            el.setPointerCapture(e.pointerId);
            const move = (ev: PointerEvent) =>
              setResizing(Math.max(60, Math.min(600, start + ev.clientX - startX)));
            const up = (ev: PointerEvent) => {
              el.removeEventListener("pointermove", move);
              el.removeEventListener("pointerup", up);
              const next = Math.max(60, Math.min(600, start + ev.clientX - startX));
              setResizing(null);
              if (next !== start) columns.update.mutate({ id: column.id, width: Math.round(next) });
            };
            el.addEventListener("pointermove", move);
            el.addEventListener("pointerup", up);
          }}
        />
      )}
      <ConfirmDialog
        open={deletingColumn}
        onOpenChange={setDeletingColumn}
        title={`Delete ${column.title}?`}
        description="Every item loses this column's values. This can't be undone."
        confirmLabel="Delete column"
        destructive
        onConfirm={() => columns.remove.mutate(column.id)}
      />
      {resizing !== null && (
        <span className="absolute -bottom-6 right-0 z-10 rounded bg-popover px-1 text-[10px] shadow">
          {Math.round(resizing)}px
        </span>
      )}
    </div>
  );
}

function Row({
  item,
  columns,
  template,
  colour,
  selected,
  onSelect,
  previous,
}: {
  item: Item;
  columns: Column[];
  template: string;
  colour: string;
  selected: boolean;
  onSelect: (on: boolean) => void;
  previous: number | null;
}) {
  const { board, canEdit, present, me, openItem } = useBoardCtx();
  const actions = useItemActions(board.id);
  const [over, setOver] = useState(false);
  const here = present.filter((p) => p.item === item.id && p.id !== me);

  return (
    <div
      role="row"
      className={cn(
        "group/row grid border-b text-sm last-of-type:border-b-0 hover:bg-muted/30",
        selected && "bg-accent/50",
        over && "border-t-2 border-t-ring",
      )}
      style={{ gridTemplateColumns: template }}
      onDragOver={(e) => {
        if (canEdit && e.dataTransfer.types.includes("text/item")) {
          e.preventDefault();
          e.stopPropagation();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setOver(false);
        const id = Number(e.dataTransfer.getData("text/item"));
        if (id && id !== item.id)
          actions.update.mutate({ id, group: item.group, before: item.id, after: previous });
      }}
    >
      <div
        className="sticky left-0 z-[1] flex items-center justify-center gap-0.5 bg-card group-hover/row:bg-muted"
        style={{ boxShadow: `inset 0 0 0 0 ${colour}` }}
      >
        {canEdit && (
          <>
            <span
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData("text/item", String(item.id));
                e.dataTransfer.effectAllowed = "move";
              }}
              className="hidden cursor-grab text-muted-foreground/60 group-hover/row:inline"
              aria-label="Drag to move"
            >
              <GripVertical className="size-3.5" />
            </span>
            <Checkbox
              aria-label={`Select ${item.name}`}
              checked={selected}
              onCheckedChange={(on) => onSelect(!!on)}
              className="group-hover/row:hidden data-checked:inline-flex"
            />
          </>
        )}
      </div>
      <div
        className="sticky z-[1] flex min-w-0 items-center gap-1 border-r bg-card pr-1 group-hover/row:bg-muted"
        style={{ left: SELECT_W }}
      >
        <ItemName item={item} />
        {here.map((p) => (
          <Avatar
            key={p.id}
            id={p.id}
            name={p.name}
            label={`${p.name} is here`}
            className="size-5"
          />
        ))}
        <button
          type="button"
          onClick={() => openItem(item.id)}
          className={cn(
            "flex shrink-0 items-center gap-0.5 rounded px-1 py-0.5 text-xs text-muted-foreground hover:bg-background hover:text-foreground",
            !item.update_count && "opacity-0 group-hover/row:opacity-100",
          )}
          aria-label={`Open ${item.name}${item.update_count ? `, ${item.update_count} updates` : ""}`}
        >
          <MessageSquare className="size-3.5" />
          {item.update_count > 0 && <span className="tabular-nums">{item.update_count}</span>}
        </button>
      </div>
      {columns.map((column) => {
        const editor = here.find((p) => p.column === column.key);
        return (
          <div
            key={column.key}
            role="cell"
            className="relative min-w-0 border-r"
            title={editor ? `${editor.name} is editing this` : undefined}
          >
            <Cell
              column={column}
              item={item}
              onChange={(value) =>
                actions.setValues.mutate({ id: item.id, values: { [column.key]: value } })
              }
            />
            {editor && (
              <>
                <span
                  aria-hidden
                  className="pointer-events-none absolute inset-0 z-[1]"
                  style={{
                    boxShadow: `inset 0 0 0 2px ${personColour(editor.id)}, inset 0 0 0 3px var(--background)`,
                  }}
                />
                <Avatar
                  id={editor.id}
                  name={editor.name}
                  label={`${editor.name} is editing this`}
                  className="pointer-events-none absolute -top-1.5 -right-1.5 z-[2] size-4 text-[8px] ring-2 ring-background"
                />
              </>
            )}
          </div>
        );
      })}
      <div />
    </div>
  );
}

function ItemName({ item }: { item: Item }) {
  const { board, canEdit, openItem, focus } = useBoardCtx();
  const actions = useItemActions(board.id);
  const [editing, setEditing] = useState(false);
  if (editing)
    return (
      <input
        autoFocus
        defaultValue={item.name}
        className="h-8 min-w-0 flex-1 rounded border bg-background px-1.5 outline-none ring-2 ring-ring"
        onBlur={(e) => {
          setEditing(false);
          focus(null, null);
          const name = e.target.value.trim();
          if (name && name !== item.name) actions.update.mutate({ id: item.id, name });
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  return (
    <button
      type="button"
      className="min-w-0 flex-1 truncate px-2 py-2 text-left hover:underline"
      onClick={() => openItem(item.id)}
      onDoubleClick={() => {
        if (canEdit) {
          setEditing(true);
          focus(item.id, "name");
        }
      }}
      title="Open, or double-click to rename"
    >
      {item.name}
    </button>
  );
}

function AddItem({ group, template }: { group: Group; template: string }) {
  const { board } = useBoardCtx();
  const actions = useItemActions(board.id);
  const [name, setName] = useState("");
  const add = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    actions.create.mutate({ name: trimmed, group: group.id }, { onSuccess: () => setName("") });
  };
  return (
    <div className="grid border-b" style={{ gridTemplateColumns: template }}>
      <div className="sticky left-0 bg-card" />
      <div className="sticky z-[1] border-r bg-card" style={{ left: SELECT_W }}>
        <input
          value={name}
          placeholder="+ Add item"
          aria-label={`Add an item to ${group.name}`}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          onBlur={add}
          className="h-9 w-full bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground focus:bg-background"
        />
      </div>
    </div>
  );
}

/** Under each group: a battery of status labels, and sums of numbers. */
function Summary({
  items,
  columns,
  template,
}: {
  items: Item[];
  columns: Column[];
  template: string;
}) {
  if (!items.length) return null;
  return (
    <div className="grid bg-muted/20 text-xs" style={{ gridTemplateColumns: template }}>
      <div className="sticky left-0 bg-card" />
      <div className="sticky z-[1] border-r bg-card" style={{ left: SELECT_W }} />
      {columns.map((column) => (
        <div key={column.key} className="flex min-h-8 items-center border-r px-2">
          <ColumnSummary column={column} items={items} />
        </div>
      ))}
      <div />
    </div>
  );
}

function ColumnSummary({ column, items }: { column: Column; items: Item[] }) {
  if (column.type === "status") {
    const counts = new Map<string, number>();
    for (const item of items) {
      const id = str(item.values[column.key]);
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
    const parts = [...labelsOf(column).map((l) => l.id), ""].filter((id) => counts.has(id));
    return (
      <div
        className="flex h-4 w-full overflow-hidden rounded-sm"
        title={parts
          .map((id) => `${findLabel(column, id)?.label ?? "No status"}: ${counts.get(id)}`)
          .join(", ")}
      >
        {parts.map((id) => (
          <span
            key={id || "none"}
            style={{
              flexGrow: counts.get(id),
              background: id ? labelColour(findLabel(column, id)?.colour) : "var(--muted)",
            }}
          />
        ))}
      </div>
    );
  }
  if (column.type === "number" || column.type === "formula") {
    const numbers = items
      .map((i) => Number(i.values[column.key]))
      .filter((n) => Number.isFinite(n));
    if (!numbers.length) return null;
    const sum = numbers.reduce((a, b) => a + b, 0);
    return (
      <span className="w-full text-right font-medium tabular-nums">
        {column.type === "number"
          ? formatNumber(sum, column)
          : `${column.settings.unit ? `${column.settings.unit} ` : ""}${formatNumber(sum)}`}
        <span className="block text-[10px] font-normal text-muted-foreground">sum</span>
      </span>
    );
  }
  if (column.type === "checkbox") {
    const done = items.filter((i) => i.values[column.key]).length;
    return (
      <span className="w-full text-center tabular-nums">
        {done}/{items.length}
      </span>
    );
  }
  return <Fragment />;
}
