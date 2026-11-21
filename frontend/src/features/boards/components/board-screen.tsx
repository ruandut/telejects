/**
 * A board: its saved views (table or kanban), search, filters and sorting, who else is here,
 * bulk changes, automations, import and the board's activity. Changes from others arrive live.
 */
import {
  Activity as ActivityIcon,
  Archive,
  Bot,
  FileUp,
  Kanban as KanbanIcon,
  MapPinned,
  MoreHorizontal,
  Pencil,
  Plus,
  Save,
  Table2,
  Trash2,
  X,
} from "lucide-react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { NativeSelect } from "@/components/form";
import { NameDialog } from "@/components/name-dialog";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { AutomationsPanel } from "@/features/automations/components/automations-panel";
import { useProjectPeople } from "@/features/projects/api";
import { atLeast } from "@/features/projects/types";
import { usePermission } from "@/features/realms/permissions";
import { cn } from "@/lib/utils";

import {
  useBoard,
  useBoardActivity,
  useBoardLive,
  useDeleteBoard,
  useItemActions,
  useItems,
  usePresence,
  useUpdateBoard,
  useViewActions,
} from "../api";
import { BoardContext, type BoardCtx } from "../board-context";
import type { Board, BoardView, Item, ViewConfig } from "../types";
import { labelsOf, matches, sortKey, textOf } from "../values";
import { Avatar } from "./avatar";
import { BoardTable } from "./board-table";
import { FilterBar } from "./filter-bar";
import { ImportDialog } from "./import-dialog";
import { ActivityLine, ItemDrawer } from "./item-drawer";
import { Kanban } from "./kanban";

const NO_CONFIG: ViewConfig = {};

export function BoardScreen({
  boardId,
  viewId,
  itemId,
  onView,
  onItem,
}: {
  boardId: number;
  viewId: number | undefined;
  itemId: number | undefined;
  onView: (id: number) => void;
  onItem: (id: number | undefined) => void;
}) {
  const board = useBoard(boardId);
  const items = useItems(boardId);
  useBoardLive(boardId);
  if (board.error)
    return (
      <p role="alert" className="p-6 text-sm text-destructive">
        {board.error.message}
      </p>
    );
  if (!board.data || !items.data)
    return (
      <div className="grid gap-3 p-4">
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-64" />
      </div>
    );
  return (
    <Loaded
      board={board.data}
      items={items.data}
      viewId={viewId}
      itemId={itemId}
      onView={onView}
      onItem={onItem}
    />
  );
}

function Loaded({
  board,
  items,
  viewId,
  itemId,
  onView,
  onItem,
}: {
  board: Board;
  items: Item[];
  viewId: number | undefined;
  itemId: number | undefined;
  onView: (id: number) => void;
  onItem: (id: number | undefined) => void;
}) {
  const me = useMe().data?.realm?.membership ?? null;
  const people = useProjectPeople(board.project.id);
  const [focusAt, setFocusAt] = useState<{ item: number | null; column: string | null }>({
    item: null,
    column: null,
  });
  const present = usePresence(board.id, focusAt);
  const view = board.views.find((v) => v.id === viewId) ?? board.views[0];
  // Unsaved changes to the view, until another view is chosen or the saved one changes.
  const viewKey = `${view?.id}:${JSON.stringify(view?.config ?? {})}`;
  const [edits, setEdits] = useState<{ key: string; config: ViewConfig } | null>(null);
  const draft = edits?.key === viewKey ? edits.config : (view?.config ?? NO_CONFIG);
  const setDraft = (config: ViewConfig) => setEdits({ key: viewKey, config });
  const dirty = JSON.stringify(draft) !== JSON.stringify(view?.config ?? {});
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [panel, setPanel] = useState<"automations" | "activity" | "import" | null>(null);
  const viewActions = useViewActions(board.id);
  const updateBoard = useUpdateBoard(board.id);
  const deleteBoard = useDeleteBoard(board.id, board.project.id);
  const navigate = useNavigate();
  const [boardDialog, setBoardDialog] = useState<"rename" | "delete" | null>(null);
  const canEdit = atLeast(board.my_level, "edit");
  const canManage = board.my_level === "manage";

  const peopleList = useMemo(() => people.data ?? [], [people.data]);
  const peopleMap = useMemo(() => new Map(peopleList.map((p) => [p.id, p])), [peopleList]);
  const focus = useCallback(
    (item: number | null, column: string | null) => setFocusAt({ item, column }),
    [],
  );
  const ctx: BoardCtx = {
    board,
    people: peopleMap,
    peopleList,
    canEdit,
    canManage,
    present,
    me,
    focus,
    openItem: (id) => onItem(id),
  };

  const columns = board.columns.filter((c) => !(draft.hidden ?? []).includes(c.key));
  const shown = useMemo(() => {
    const needle = (draft.search ?? "").trim().toLowerCase();
    let rows = items.filter((item) => {
      if (
        needle &&
        !`${item.name} ${board.columns.map((c) => textOf(c, item.values[c.key], peopleMap)).join(" ")}`
          .toLowerCase()
          .includes(needle)
      )
        return false;
      return (draft.filters ?? []).every((f) =>
        matches(
          board.columns.find((c) => c.key === f.column),
          item,
          f,
          peopleMap,
        ),
      );
    });
    const sort = draft.sort ?? [];
    if (sort.length) {
      rows = [...rows].sort((a, b) => {
        for (const s of sort) {
          const column = board.columns.find((c) => c.key === s.column);
          const x = sortKey(column, a, peopleMap);
          const y = sortKey(column, b, peopleMap);
          if (x < y) return s.dir === "asc" ? -1 : 1;
          if (x > y) return s.dir === "asc" ? 1 : -1;
        }
        return 0;
      });
    } else rows = [...rows].sort((a, b) => a.position - b.position || a.id - b.id);
    return rows;
  }, [items, draft, board.columns, peopleMap]);

  const openItem = items.find((i) => i.id === itemId) ?? null;
  const others = present.filter((p) => p.id !== me);
  const kanbanColumn =
    board.columns.find((c) => c.key === (draft.kanban_column ?? board.status_column)) ??
    board.columns.find((c) => c.type === "status");

  return (
    <BoardContext.Provider value={ctx}>
      <div className="grid min-w-0 gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <nav aria-label="Views" className="flex min-w-0 items-center gap-1 overflow-x-auto">
            {board.views.map((v) => (
              <ViewTab
                key={v.id}
                view={v}
                active={v.id === view?.id}
                onClick={() => onView(v.id)}
                canManage={canManage}
                onDelete={() => viewActions.remove.mutate(v.id)}
                onRename={(name) => viewActions.update.mutate({ id: v.id, name })}
              />
            ))}
            {canManage && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" aria-label="Add a view">
                    <Plus />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    onSelect={() =>
                      viewActions.create.mutate(
                        { name: "Table", kind: "table", config: draft },
                        { onSuccess: (v) => onView(v.id) },
                      )
                    }
                  >
                    <Table2 /> Table view
                  </DropdownMenuItem>
                  {board.columns.some((c) => c.type === "status") && (
                    <DropdownMenuItem
                      onSelect={() =>
                        viewActions.create.mutate(
                          {
                            name: "Kanban",
                            kind: "kanban",
                            config: { ...draft, kanban_column: kanbanColumn?.key },
                          },
                          { onSuccess: (v) => onView(v.id) },
                        )
                      }
                    >
                      <KanbanIcon /> Kanban view
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </nav>
          {board.feasibility_run && <BoardRunLink run={board.feasibility_run} />}
          <div className="ml-auto flex items-center gap-2">
            {others.length > 0 && (
              <div
                className="flex items-center -space-x-1.5"
                aria-label={`${others.length} others on this board`}
              >
                {others.slice(0, 5).map((p) => (
                  <span key={p.id} className="relative">
                    <Avatar id={p.id} name={p.name} label={`${p.name} is on this board`} ring />
                    <span className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-label-green ring-2 ring-background" />
                  </span>
                ))}
              </div>
            )}
            <Button variant="outline" size="sm" onClick={() => setPanel("automations")}>
              <Bot /> <span className="hidden sm:inline">Automate</span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="More">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setPanel("activity")}>
                  <ActivityIcon /> Board activity
                </DropdownMenuItem>
                {canEdit && (
                  <DropdownMenuItem onSelect={() => setPanel("import")}>
                    <FileUp /> Import from a file
                  </DropdownMenuItem>
                )}
                {canManage && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setBoardDialog("rename")}>
                      <Pencil /> Rename board
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={() => setBoardDialog("delete")}
                    >
                      <Trash2 /> Delete board
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {canEdit && view?.kind !== "kanban" && (
            <Button
              size="sm"
              onClick={() =>
                document
                  .querySelector<HTMLInputElement>('input[aria-label^="Add an item"]')
                  ?.focus()
              }
            >
              <Plus /> New item
            </Button>
          )}
          <SearchInput
            label="Search this board"
            placeholder="Search"
            className="w-40 sm:w-56"
            value={draft.search ?? ""}
            onChange={(search) => setDraft({ ...draft, search })}
          />
          <FilterBar config={draft} onChange={setDraft} />
          {view?.kind === "kanban" && (
            <NativeSelect
              aria-label="Lanes by"
              className="h-8 w-40"
              value={kanbanColumn?.key ?? ""}
              onChange={(e) => setDraft({ ...draft, kanban_column: e.target.value })}
            >
              {board.columns
                .filter((c) => c.type === "status")
                .map((c) => (
                  <option key={c.key} value={c.key}>
                    Lanes: {c.title}
                  </option>
                ))}
            </NativeSelect>
          )}
          {dirty && (
            <div className="flex items-center gap-1">
              {canManage && view && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => viewActions.update.mutate({ id: view.id, config: draft })}
                >
                  <Save /> Save view
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setDraft(view?.config ?? {})}>
                Reset
              </Button>
            </div>
          )}
          <span className="ml-auto text-xs text-muted-foreground tabular-nums">
            {shown.length === items.length
              ? `${items.length} items`
              : `${shown.length} of ${items.length} items`}
          </span>
        </div>

        {view?.kind === "kanban" && kanbanColumn ? (
          <Kanban items={shown} column={kanbanColumn} columns={columns} />
        ) : (
          <BoardTable
            items={shown}
            columns={columns}
            groups={board.groups}
            selected={selected}
            onSelect={(ids, on) =>
              setSelected((prev) => {
                const next = new Set(prev);
                for (const id of ids) {
                  if (on) next.add(id);
                  else next.delete(id);
                }
                return next;
              })
            }
            onHide={(key) => setDraft({ ...draft, hidden: [...(draft.hidden ?? []), key] })}
          />
        )}
      </div>

      {selected.size > 0 && (
        <BulkBar board={board} ids={[...selected]} onDone={() => setSelected(new Set())} />
      )}
      <ItemDrawer item={openItem} onClose={() => onItem(undefined)} />
      <AutomationsPanel
        board={board}
        people={peopleList}
        open={panel === "automations"}
        onOpenChange={(open) => setPanel(open ? "automations" : null)}
      />
      {panel === "import" && <ImportDialog onClose={() => setPanel(null)} />}
      {boardDialog === "rename" && (
        <NameDialog
          title="Rename board"
          initial={board.name}
          pending={updateBoard.isPending}
          onClose={() => setBoardDialog(null)}
          onSubmit={(name) =>
            updateBoard.mutate({ name }, { onSuccess: () => setBoardDialog(null) })
          }
        />
      )}
      <ConfirmDialog
        open={boardDialog === "delete"}
        onOpenChange={(open) => setBoardDialog(open ? "delete" : null)}
        title={`Delete ${board.name}?`}
        description={`Its ${items.length} item${items.length === 1 ? "" : "s"}, their updates and activity, its views and its automations are deleted with it. This can't be undone.`}
        confirmLabel="Delete board"
        destructive
        typeToConfirm={board.name}
        onConfirm={() =>
          deleteBoard.mutate(undefined, {
            onSuccess: () =>
              void navigate({
                to: "/projects/$projectId",
                params: { projectId: String(board.project.id) },
              }),
          })
        }
      />
      <BoardActivity board={board} open={panel === "activity"} onClose={() => setPanel(null)} />
    </BoardContext.Provider>
  );
}

function ViewTab({
  view,
  active,
  onClick,
  canManage,
  onDelete,
  onRename,
}: {
  view: BoardView;
  active: boolean;
  onClick: () => void;
  canManage: boolean;
  onDelete: () => void;
  onRename: (name: string) => void;
}) {
  const Icon = view.kind === "kanban" ? KanbanIcon : Table2;
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  return (
    <div
      className={cn(
        "group flex shrink-0 items-center rounded-md border-b-2 border-transparent",
        active && "border-primary",
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex items-center gap-1.5 px-2 py-1.5 text-sm",
          active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
        )}
        aria-current={active ? "page" : undefined}
      >
        <Icon className="size-4" /> {view.name}
      </button>
      {canManage && active && (
        <DropdownMenu>
          <DropdownMenuTrigger
            className="rounded p-0.5 text-muted-foreground hover:bg-muted"
            aria-label={`${view.name} options`}
          >
            <MoreHorizontal className="size-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => setRenaming(true)}>Rename</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}>
              <Trash2 /> Delete view
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete the ${view.name} view?`}
        description="Only the view goes: its filters, sort and hidden columns. The board's items stay."
        confirmLabel="Delete view"
        destructive
        onConfirm={onDelete}
      />
      {renaming && (
        <NameDialog
          title="Rename view"
          initial={view.name}
          onClose={() => setRenaming(false)}
          onSubmit={(name) => {
            onRename(name);
            setRenaming(false);
          }}
        />
      )}
    </div>
  );
}

/** Where this board's items came from: a feasibility run, linked when I may open it. */
function BoardRunLink({ run }: { run: { id: number; name: string } }) {
  const canOpen = usePermission("feasibilities.view");
  const label = (
    <>
      <MapPinned className="size-3.5" /> From {run.name}
    </>
  );
  return canOpen ? (
    <Link
      to="/feasibilities/$runId"
      params={{ runId: String(run.id) }}
      className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
    >
      {label}
    </Link>
  ) : (
    <span className="flex shrink-0 items-center gap-1 px-2 py-1 text-xs text-muted-foreground">
      {label}
    </span>
  );
}

function BulkBar({ board, ids, onDone }: { board: Board; ids: number[]; onDone: () => void }) {
  const actions = useItemActions(board.id);
  const status =
    board.columns.find((c) => c.key === board.status_column) ??
    board.columns.find((c) => c.type === "status");
  const run = (input: { action: string; group?: number; values?: Record<string, unknown> }) =>
    actions.batch.mutate({ items: ids, ...input }, { onSuccess: onDone });
  return (
    <div
      role="toolbar"
      aria-label="Selected items"
      className="fixed inset-x-3 bottom-4 z-30 mx-auto flex max-w-3xl flex-wrap items-center gap-2 rounded-xl border bg-popover p-2 shadow-lg"
    >
      <span className="px-2 text-sm font-medium tabular-nums">{ids.length} selected</span>
      {status && (
        <NativeSelect
          aria-label={`Set ${status.title}`}
          className="h-8 w-40"
          value=""
          onChange={(e) =>
            e.target.value && run({ action: "set", values: { [status.key]: e.target.value } })
          }
        >
          <option value="">Set {status.title}…</option>
          {labelsOf(status).map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </NativeSelect>
      )}
      <NativeSelect
        aria-label="Move to group"
        className="h-8 w-40"
        value=""
        onChange={(e) => e.target.value && run({ action: "move", group: Number(e.target.value) })}
      >
        <option value="">Move to…</option>
        {board.groups.map((g) => (
          <option key={g.id} value={g.id}>
            {g.name}
          </option>
        ))}
      </NativeSelect>
      <Button size="sm" variant="ghost" onClick={() => run({ action: "duplicate" })}>
        Duplicate
      </Button>
      <Button size="sm" variant="ghost" onClick={() => run({ action: "archive" })}>
        <Archive /> Archive
      </Button>
      <ConfirmDialog
        title={`Delete ${ids.length} item${ids.length === 1 ? "" : "s"}?`}
        description="Their values, updates and activity go with them. This can't be undone; archive them to keep them."
        confirmLabel="Delete"
        destructive
        onConfirm={() => run({ action: "delete" })}
      >
        <Button size="sm" variant="ghost" className="text-destructive">
          <Trash2 /> Delete
        </Button>
      </ConfirmDialog>
      <Button
        size="icon"
        variant="ghost"
        className="ml-auto"
        aria-label="Clear selection"
        onClick={onDone}
      >
        <X />
      </Button>
    </div>
  );
}

function BoardActivity({
  board,
  open,
  onClose,
}: {
  board: Board;
  open: boolean;
  onClose: () => void;
}) {
  const activity = useBoardActivity(board.id, open);
  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Activity on {board.name}</SheetTitle>
          <SheetDescription>The latest 100 changes, by people and automations.</SheetDescription>
        </SheetHeader>
        <ul className="px-4 pb-6">
          {activity.data?.map((a) => (
            <div key={a.id}>
              <p className="pt-2 text-xs font-medium text-primary">{a.item_name}</p>
              <ActivityLine a={a} />
            </div>
          ))}
        </ul>
      </SheetContent>
    </Sheet>
  );
}
