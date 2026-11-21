/** Automations as sentences, the way monday.com reads them back. */
import type { Board, Column } from "@/features/boards/types";
import { str, findLabel } from "@/features/boards/values";

import type { Action, Automation, Condition, Trigger } from "./types";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const col = (board: Board, key: string | null | undefined): Column | undefined =>
  board.columns.find((c) => c.key === key);
const title = (board: Board, key: string | null | undefined) =>
  key === "name" ? "Item name" : (col(board, key)?.title ?? "a column");

export function describeTrigger(board: Board, t: Trigger): string {
  switch (t.type) {
    case "item_created":
      return "When an item is created";
    case "column_changed":
      return t.column ? `When ${title(board, t.column)} changes` : "When any column changes";
    case "status_changed": {
      const c = col(board, t.column);
      const to = t.to.map((id) => (c ? findLabel(c, id)?.label : id)).filter(Boolean);
      return `When ${title(board, t.column)} changes${to.length ? ` to ${to.join(" or ")}` : ""}`;
    }
    case "item_moved":
      return t.group
        ? `When an item moves to ${board.groups.find((g) => g.id === t.group)?.name ?? "a group"}`
        : "When an item moves to another group";
    case "date_arrives":
      return t.when === "on"
        ? `When ${title(board, t.column)} arrives, at ${t.time}`
        : `${t.days} day${t.days === 1 ? "" : "s"} ${t.when} ${title(board, t.column)}, at ${t.time}`;
    case "schedule":
      return t.every === "week"
        ? `Every ${WEEKDAYS[t.weekday ?? 0]} at ${t.time}`
        : t.every === "month"
          ? `On day ${t.day} of every month at ${t.time}`
          : t.every === "weekday"
            ? `Every weekday at ${t.time}`
            : `Every day at ${t.time}`;
  }
}

export function describeCondition(board: Board, c: Condition): string {
  if (c.column === "group")
    return `the item is ${c.op === "is" ? "in" : "not in"} ${board.groups.find((g) => g.id === c.value)?.name ?? "a group"}`;
  const column = col(board, c.column);
  const value =
    column && (column.type === "status" || column.type === "dropdown")
      ? (findLabel(column, c.value)?.label ?? String(c.value))
      : str(c.value);
  const op =
    {
      is: "is",
      is_not: "is not",
      contains: "contains",
      is_empty: "is empty",
      is_not_empty: "is not empty",
      gt: "is more than",
      lt: "is less than",
      gte: "is at least",
      lte: "is at most",
    }[c.op] ?? c.op;
  return `${title(board, c.column)} ${op}${["is_empty", "is_not_empty"].includes(c.op) ? "" : ` ${value}`}`;
}

export function describeAction(board: Board, a: Action): string {
  switch (a.type) {
    case "set_value": {
      const column = col(board, a.column);
      let value = str(a.value);
      if (a.value && typeof a.value === "object" && "today_plus" in (a.value as object)) {
        const n = (a.value as { today_plus: number }).today_plus;
        value = n === 0 ? "today" : `today ${n > 0 ? "+" : "−"} ${Math.abs(n)} days`;
      } else if (column?.type === "status") value = findLabel(column, a.value)?.label ?? value;
      else if (a.value === "trigger_person") value = "the person who made the change";
      else if (a.value === "creator") value = "the item's creator";
      return `set ${title(board, a.column)} to ${value}`;
    }
    case "clear_value":
      return `clear ${title(board, a.column)}`;
    case "copy_value":
      return `copy ${title(board, a.from)} to ${title(board, a.to)}`;
    case "increment":
      return `add ${a.by} to ${title(board, a.column)}`;
    case "move_to_group":
      return `move the item to ${board.groups.find((g) => g.id === a.group)?.name ?? "a group"}`;
    case "notify": {
      const who = [
        a.people_column && `the item's ${title(board, a.people_column)}`,
        a.members.length && `${a.members.length} chosen people`,
        a.trigger_person && "whoever changed it",
      ].filter(Boolean);
      return `notify ${who.join(" and ")}`;
    }
    case "create_item":
      return `create an item on another board`;
    case "archive_item":
      return "archive the item";
  }
}

export function describe(board: Board, a: Automation): string {
  const parts = [describeTrigger(board, a.trigger)];
  if (a.conditions.length)
    parts.push(`and only if ${a.conditions.map((c) => describeCondition(board, c)).join(" and ")}`);
  const wait = a.delay ? `wait ${a.delay.amount} ${a.delay.unit}, then ` : "";
  parts.push(`${wait}${a.actions.map((x) => describeAction(board, x)).join(", then ")}`);
  return parts.join(", ");
}
