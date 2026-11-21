/** The board as cards in lanes, one lane per label of a status column. Drag a card to change it. */
import { MessageSquare } from "lucide-react";
import { useMemo, useState } from "react";

import { labelColour } from "@/lib/colours";
import { cn } from "@/lib/utils";

import { useItemActions } from "../api";
import { useBoardCtx } from "../board-context";
import type { Column, Item } from "../types";
import { formatDate, labelsOf, textOf } from "../values";
import { AvatarStack } from "./avatar";

export function Kanban({
  items,
  column,
  columns,
}: {
  items: Item[];
  column: Column;
  columns: Column[];
}) {
  const { board, canEdit } = useBoardCtx();
  const actions = useItemActions(board.id);
  const [over, setOver] = useState<string | null>(null);
  const lanes = useMemo(() => {
    const labels = labelsOf(column);
    const known = new Set(labels.map((l) => l.id));
    return [{ id: "", label: "No status", colour: "" }, ...labels].map((lane) => ({
      ...lane,
      items: items.filter((i) => {
        const value = i.values[column.key] as string | undefined;
        return lane.id ? value === lane.id : !value || !known.has(value);
      }),
    }));
  }, [items, column]);

  return (
    <div className="flex gap-3 overflow-x-auto pb-4">
      {lanes
        .filter((lane) => lane.id || lane.items.length)
        .map((lane) => (
          <section
            key={lane.id || "none"}
            aria-label={lane.label}
            className={cn(
              "flex w-72 shrink-0 flex-col rounded-lg bg-muted/40",
              over === lane.id && "ring-2 ring-ring/50",
            )}
            onDragOver={(e) => {
              if (canEdit && e.dataTransfer.types.includes("text/item")) {
                e.preventDefault();
                setOver(lane.id);
              }
            }}
            onDragLeave={() => setOver(null)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(null);
              const id = Number(e.dataTransfer.getData("text/item"));
              if (id) actions.setValues.mutate({ id, values: { [column.key]: lane.id || null } });
            }}
          >
            <header
              className="flex items-center justify-between rounded-t-lg px-3 py-2 text-sm font-medium text-white"
              style={{ background: lane.id ? labelColour(lane.colour) : "var(--muted-foreground)" }}
            >
              <span className="truncate">{lane.label}</span>
              <span className="tabular-nums opacity-90">{lane.items.length}</span>
            </header>
            <div className="grid max-h-[calc(100dvh-16rem)] gap-2 overflow-y-auto p-2">
              {lane.items.map((item) => (
                <Card
                  key={item.id}
                  item={item}
                  columns={columns.filter((c) => c.key !== column.key)}
                />
              ))}
              {!lane.items.length && (
                <p className="p-3 text-center text-xs text-muted-foreground">Drop items here</p>
              )}
            </div>
          </section>
        ))}
    </div>
  );
}

function Card({ item, columns }: { item: Item; columns: Column[] }) {
  const { canEdit, openItem, people, board } = useBoardCtx();
  const group = board.groups.find((g) => g.id === item.group);
  const shown = columns
    .filter(
      (c) =>
        ["date", "number", "dropdown", "location", "text", "formula"].includes(c.type) &&
        item.values[c.key] != null,
    )
    .slice(0, 3);
  const assignees = columns.find((c) => c.type === "people");
  const ids = (assignees ? (item.values[assignees.key] as number[] | undefined) : undefined) ?? [];
  return (
    <article
      draggable={canEdit}
      onDragStart={(e) => {
        e.dataTransfer.setData("text/item", String(item.id));
        e.dataTransfer.effectAllowed = "move";
      }}
      onClick={() => openItem(item.id)}
      className="cursor-pointer rounded-md border bg-card p-3 text-sm shadow-xs hover:border-ring/50"
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="min-w-0 font-medium break-words">{item.name}</h4>
        {group && (
          <span
            className="mt-1 size-2 shrink-0 rounded-full"
            style={{ background: labelColour(group.colour) }}
            title={group.name}
          />
        )}
      </div>
      <dl className="mt-2 grid gap-1 text-xs">
        {shown.map((c) => (
          <div key={c.key} className="flex justify-between gap-2">
            <dt className="text-muted-foreground">{c.title}</dt>
            <dd className="truncate tabular-nums">
              {c.type === "date"
                ? formatDate(item.values[c.key])
                : textOf(c, item.values[c.key], people)}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-2 flex items-center justify-between">
        <AvatarStack people={ids.map((id) => ({ id, name: people.get(id)?.name ?? "Someone" }))} />
        {item.update_count > 0 && (
          <span className="flex items-center gap-0.5 text-xs text-muted-foreground">
            <MessageSquare className="size-3.5" /> {item.update_count}
          </span>
        )}
      </div>
    </article>
  );
}
