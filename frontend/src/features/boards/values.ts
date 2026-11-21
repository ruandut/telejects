/**
 * Reading values on the client: how a cell reads as text, sorts and matches a filter. The server
 * is the authority on what's stored (apps/boards/column_types.py); this mirrors it for showing,
 * searching, sorting and filtering what is already loaded.
 */
import type { Person } from "@/features/projects/types";

import type { Column, Filter, Item, Label, Linked } from "./types";

/** A value as plain text for an input: numbers and text as they are, anything else blank. */
export function str(value: unknown): string {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value)
    : "";
}

export const COMPUTED = new Set(["formula", "mirror", "item_id", "created", "updated"]);

export const TYPE_LABELS: Record<string, string> = {
  status: "Status",
  text: "Text",
  long_text: "Long text",
  number: "Numbers",
  date: "Date",
  timeline: "Timeline",
  people: "People",
  dropdown: "Dropdown",
  checkbox: "Checkbox",
  rating: "Rating",
  link: "Link",
  email: "Email",
  phone: "Phone",
  location: "Location",
  connect: "Connect boards",
  mirror: "Mirror",
  formula: "Formula",
  item_id: "Item ID",
  created: "Creation log",
  updated: "Last updated",
};

export function labelsOf(column: Column): Label[] {
  return column.settings.labels ?? column.settings.options ?? [];
}

export function findLabel(column: Column, id: unknown): Label | undefined {
  return labelsOf(column).find((l) => l.id === id);
}

export function formatNumber(value: unknown, column?: Column): string {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (Number.isNaN(n)) return str(value);
  const decimals = column?.settings.decimals;
  const shown = n.toLocaleString("en-ZA", {
    minimumFractionDigits: decimals ?? 0,
    maximumFractionDigits: decimals ?? 6,
  });
  const unit = column?.settings.unit;
  if (!unit) return shown;
  return column?.settings.unit_position === "right" ? `${shown} ${unit}` : `${unit} ${shown}`;
}

export function formatDate(value: unknown): string {
  if (typeof value !== "string" || !value) return "";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
    year: sameYear ? undefined : "numeric",
  });
}

export function textOf(column: Column, value: unknown, people: Map<number, Person>): string {
  if (value === null || value === undefined) return "";
  switch (column.type) {
    case "status":
      return findLabel(column, value)?.label ?? "";
    case "dropdown":
      return (value as string[])
        .map((v) => findLabel(column, v)?.label ?? "")
        .filter(Boolean)
        .join(", ");
    case "people":
      return (value as number[]).map((id) => people.get(id)?.name ?? "Someone").join(", ");
    case "number":
      return formatNumber(value, column);
    case "formula":
      return column.settings.unit && !Number.isNaN(Number(value))
        ? `${column.settings.unit} ${formatNumber(value)}`
        : str(value);
    case "date":
      return formatDate(value);
    case "timeline": {
      const t = value as { start: string; end: string };
      return `${formatDate(t.start)} – ${formatDate(t.end)}`;
    }
    case "checkbox":
      return value ? "Yes" : "";
    case "rating":
      return `${str(value)}/${column.settings.max ?? 5}`;
    case "link": {
      const l = value as { url: string; text: string };
      return l.text || l.url;
    }
    case "location": {
      const l = value as { lat?: number; lng?: number; address?: string };
      return l.address || (l.lat !== undefined ? `${l.lat}, ${l.lng}` : "");
    }
    case "connect":
    case "mirror": {
      const linked = value as Linked;
      const shown = linked.items.map((i) => i.name ?? i.text ?? "").filter(Boolean);
      if (linked.hidden) shown.push(`${linked.hidden} hidden`);
      return shown.join(", ");
    }
    case "created":
    case "updated":
      return formatDate((value as { at?: string }).at);
    default:
      return str(value);
  }
}

export function isBlank(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object" && "items" in (value as object)) {
    const l = value as Linked;
    return !l.items.length && !l.hidden;
  }
  return false;
}

export function sortKey(
  column: Column | undefined,
  item: Item,
  people: Map<number, Person>,
): string | number {
  if (!column) return item.name.toLowerCase();
  const value = item.values[column.key];
  if (isBlank(value)) return "￿";
  if (column.type === "number" || column.type === "rating" || column.type === "item_id")
    return Number(value);
  if (column.type === "status") return labelsOf(column).findIndex((l) => l.id === value);
  if (column.type === "date") return str(value);
  if (column.type === "timeline") return (value as { start: string }).start;
  return textOf(column, value, people).toLowerCase();
}

export const FILTER_OPS: { op: string; label: string; needsValue: boolean }[] = [
  { op: "is", label: "is", needsValue: true },
  { op: "is_not", label: "is not", needsValue: true },
  { op: "contains", label: "contains", needsValue: true },
  { op: "is_empty", label: "is empty", needsValue: false },
  { op: "is_not_empty", label: "is not empty", needsValue: false },
  { op: "gt", label: "is greater than", needsValue: true },
  { op: "lt", label: "is less than", needsValue: true },
];

export function matches(
  column: Column | undefined,
  item: Item,
  filter: Filter,
  people: Map<number, Person>,
): boolean {
  if (!column) return true;
  const value = item.values[column.key];
  const wanted = str(filter.value).toLowerCase();
  const text = textOf(column, value, people).toLowerCase();
  switch (filter.op) {
    case "is_empty":
      return isBlank(value);
    case "is_not_empty":
      return !isBlank(value);
    case "contains":
      return text.includes(wanted);
    case "is":
    case "is_not": {
      let hit = text === wanted;
      if (column.type === "status")
        hit = value === filter.value || findLabel(column, value)?.label.toLowerCase() === wanted;
      if (column.type === "dropdown")
        hit =
          (value as string[] | undefined)?.some(
            (v) => v === filter.value || findLabel(column, v)?.label.toLowerCase() === wanted,
          ) ?? false;
      if (column.type === "people")
        hit = (value as number[] | undefined)?.includes(Number(filter.value)) ?? false;
      if (column.type === "checkbox") hit = !!value === ["true", "yes", "checked"].includes(wanted);
      return filter.op === "is" ? hit : !hit;
    }
    case "gt":
    case "lt": {
      const a = column.type === "date" ? str(value) : Number(value);
      const b = column.type === "date" ? str(filter.value) : Number(filter.value);
      if (isBlank(value)) return false;
      return filter.op === "gt" ? a > b : a < b;
    }
    default:
      return true;
  }
}
