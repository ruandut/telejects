/** One item, opened from the board: every value, its updates (with @mentions) and its activity. */
import { Archive, ArchiveRestore, AtSign, Copy, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { labelColour } from "@/lib/colours";

import { useItemActions, useItemActivity, useItemUpdates, usePostUpdate } from "../api";
import { useBoardCtx } from "../board-context";
import type { Activity, Item } from "../types";
import { Avatar } from "./avatar";
import { Cell } from "./cells";

function when(at: string): string {
  const date = new Date(at);
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return date.toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

export function ItemDrawer({ item, onClose }: { item: Item | null; onClose: () => void }) {
  return (
    <Sheet open={!!item} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        onOpenAutoFocus={(e) => e.preventDefault()}
        className="w-full gap-0 overflow-y-auto p-0 sm:max-w-xl data-[side=right]:sm:max-w-xl"
      >
        {item && <ItemBody item={item} onClose={onClose} />}
      </SheetContent>
    </Sheet>
  );
}

function ItemBody({ item, onClose }: { item: Item; onClose: () => void }) {
  const { board, canEdit, focus } = useBoardCtx();
  const actions = useItemActions(board.id);
  const group = board.groups.find((g) => g.id === item.group);
  const [name, setName] = useState(item.name);
  return (
    <>
      <SheetHeader className="border-b p-4 pr-12">
        <SheetDescription className="flex items-center gap-2 text-xs">
          {group && (
            <span
              className="size-2 rounded-full"
              style={{ background: labelColour(group.colour) }}
            />
          )}
          {group?.name} · #{item.number}
        </SheetDescription>
        <SheetTitle className="sr-only">{item.name}</SheetTitle>
        {canEdit ? (
          <input
            value={name}
            aria-label="Item name"
            onChange={(e) => setName(e.target.value)}
            onFocus={() => focus(item.id, "name")}
            onBlur={() => {
              focus(null, null);
              if (name.trim() && name.trim() !== item.name)
                actions.update.mutate({ id: item.id, name: name.trim() });
            }}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className="rounded-md bg-transparent text-xl font-semibold outline-none focus:ring-2 focus:ring-ring"
          />
        ) : (
          <p className="text-xl font-semibold">{item.name}</p>
        )}
        {canEdit && (
          <div className="flex flex-wrap gap-1">
            {item.archived_at ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => actions.act.mutate({ id: item.id, action: "restore" })}
              >
                <ArchiveRestore /> Restore
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  actions.act.mutate({ id: item.id, action: "archive" }, { onSuccess: onClose })
                }
              >
                <Archive /> Archive
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => actions.act.mutate({ id: item.id, action: "duplicate" })}
            >
              <Copy /> Duplicate
            </Button>
            <ConfirmDialog
              title={`Delete ${item.name}?`}
              description="Its values, updates and activity go with it. This can't be undone; archive it to keep them."
              confirmLabel="Delete item"
              destructive
              onConfirm={() => actions.remove.mutate(item.id, { onSuccess: onClose })}
            >
              <Button variant="ghost" size="sm" className="text-destructive">
                <Trash2 /> Delete
              </Button>
            </ConfirmDialog>
          </div>
        )}
      </SheetHeader>
      <Tabs defaultValue="details" className="p-4">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="updates">
            Updates{item.update_count ? ` (${item.update_count})` : ""}
          </TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>
        <TabsContent value="details" className="mt-3">
          <dl className="grid gap-px overflow-hidden rounded-lg border bg-border">
            {board.columns.map((column) => (
              <div
                key={column.key}
                className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] bg-card"
              >
                <dt className="flex items-center px-3 py-2 text-xs text-muted-foreground">
                  {column.title}
                </dt>
                <dd className="min-w-0 border-l">
                  <Cell
                    wide
                    column={column}
                    item={item}
                    onChange={(value) =>
                      actions.setValues.mutate({ id: item.id, values: { [column.key]: value } })
                    }
                  />
                </dd>
              </div>
            ))}
          </dl>
        </TabsContent>
        <TabsContent value="updates" className="mt-3">
          <Updates item={item} />
        </TabsContent>
        <TabsContent value="activity" className="mt-3">
          <ActivityList item={item} />
        </TabsContent>
      </Tabs>
    </>
  );
}

function Updates({ item }: { item: Item }) {
  const { board, canEdit, peopleList } = useBoardCtx();
  const updates = useItemUpdates(item.id, board.id);
  const post = usePostUpdate(item.id, board.id);
  const [body, setBody] = useState("");
  const [mentions, setMentions] = useState<number[]>([]);
  const [picking, setPicking] = useState(false);
  const query = /@(\w*)$/.exec(body)?.[1]?.toLowerCase();
  const suggestions = useMemo(
    () =>
      query !== undefined || picking
        ? peopleList.filter((p) => p.name.toLowerCase().includes(query ?? "")).slice(0, 6)
        : [],
    [query, picking, peopleList],
  );
  const mention = (id: number, name: string) => {
    setBody((text) => `${text.replace(/@\w*$/, "")}@${name.split(" ")[0]} `);
    setMentions((ids) => (ids.includes(id) ? ids : [...ids, id]));
    setPicking(false);
  };

  return (
    <div className="grid gap-4">
      {canEdit && (
        <div className="relative grid gap-2">
          <Textarea
            value={body}
            rows={3}
            placeholder="Write an update. Type @ to mention someone."
            aria-label="New update"
            onChange={(e) => setBody(e.target.value)}
          />
          {suggestions.length > 0 && (
            <div className="absolute top-full z-10 mt-1 grid w-64 gap-0.5 rounded-md border bg-popover p-1 shadow-md">
              {suggestions.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="flex items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
                  onClick={() => mention(p.id, p.name)}
                >
                  <Avatar id={p.id} name={p.name} /> {p.name}
                </button>
              ))}
            </div>
          )}
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => setPicking((v) => !v)}>
              <AtSign /> Mention
            </Button>
            <Button
              size="sm"
              disabled={!body.trim() || post.isPending}
              onClick={() =>
                post.mutate(
                  { body, mentions },
                  {
                    onSuccess: () => {
                      setBody("");
                      setMentions([]);
                    },
                  },
                )
              }
            >
              Post update
            </Button>
          </div>
        </div>
      )}
      {updates.isLoading && <Skeleton className="h-20" />}
      {updates.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">No updates yet.</p>
      )}
      {updates.data?.map((u) => (
        <article key={u.id} className="rounded-lg border bg-card p-3">
          <header className="flex items-center gap-2 text-sm">
            {u.author && <Avatar id={u.author} name={u.author_name} />}
            <span className="font-medium">{u.author_name}</span>
            <time className="ml-auto text-xs text-muted-foreground" dateTime={u.created_at}>
              {when(u.created_at)}
            </time>
          </header>
          <p className="mt-2 text-sm break-words whitespace-pre-wrap">{u.body}</p>
        </article>
      ))}
    </div>
  );
}

export function ActivityLine({ a }: { a: Activity }) {
  const what =
    a.kind === "value"
      ? `changed ${a.column_title}`
      : a.kind === "created"
        ? "created it"
        : a.kind === "name"
          ? "renamed it"
          : a.kind === "moved"
            ? "moved it"
            : a.kind === "update"
              ? "wrote an update"
              : a.kind;
  return (
    <li className="grid gap-0.5 border-b py-2 text-sm last:border-b-0">
      <div className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="font-medium">{a.who}</span>
        <span className="text-muted-foreground">{what}</span>
        <time className="ml-auto text-xs text-muted-foreground" dateTime={a.at}>
          {when(a.at)}
        </time>
      </div>
      {(a.old_text || a.new_text) && a.kind !== "created" && a.kind !== "update" && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="rounded bg-muted px-1.5 py-0.5 line-through decoration-muted-foreground/60">
            {a.old_text || "empty"}
          </span>
          <span aria-hidden>→</span>
          <span className="rounded bg-accent px-1.5 py-0.5">{a.new_text || "empty"}</span>
        </div>
      )}
      {a.kind === "update" && (
        <p className="line-clamp-2 text-xs text-muted-foreground">{a.new_text}</p>
      )}
    </li>
  );
}

function ActivityList({ item }: { item: Item }) {
  const { board } = useBoardCtx();
  const activity = useItemActivity(item.id, board.id);
  if (activity.isLoading) return <Skeleton className="h-20" />;
  return (
    <ul>
      {activity.data?.map((a) => (
        <ActivityLine key={a.id} a={a} />
      ))}
    </ul>
  );
}
