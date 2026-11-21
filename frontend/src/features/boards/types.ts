import type { Level } from "@/features/projects/types";

export type ColumnType =
  | "status"
  | "text"
  | "long_text"
  | "number"
  | "date"
  | "timeline"
  | "people"
  | "dropdown"
  | "checkbox"
  | "rating"
  | "link"
  | "email"
  | "phone"
  | "location"
  | "connect"
  | "mirror"
  | "formula"
  | "item_id"
  | "created"
  | "updated";

export type Label = { id: string; label: string; colour: string; done: boolean };

export type ColumnSettings = {
  labels?: Label[];
  options?: Label[];
  unit?: string;
  unit_position?: "left" | "right";
  decimals?: number | null;
  max?: number;
  expression?: string;
  board?: number;
  connect_column?: string;
  target_column?: string;
};

export type Column = {
  id: number;
  key: string;
  title: string;
  type: ColumnType;
  settings: ColumnSettings;
  description: string;
  position: number;
  width: number;
};

export type Group = { id: number; name: string; colour: string; position: number };

export type Filter = { column: string; op: string; value: unknown };

export type ViewConfig = {
  search?: string;
  filters?: Filter[];
  sort?: { column: string; dir: "asc" | "desc" }[];
  hidden?: string[];
  kanban_column?: string;
};

export type BoardView = {
  id: number;
  name: string;
  kind: "table" | "kanban";
  config: ViewConfig;
  position: number;
};

export type Board = {
  id: number;
  name: string;
  description: string;
  project: { id: number; name: string; client: string; colour: string };
  status_column: string;
  due_column: string;
  my_level: Level;
  /** The feasibility run its items were made from. */
  feasibility_run: { id: number; name: string } | null;
  groups: Group[];
  columns: Column[];
  views: BoardView[];
};

export type BoardSummary = {
  id: number;
  name: string;
  description: string;
  position: number;
  item_count: number | null;
  done_count: number | null;
  feasibility_run: number | null;
};

export type Linked = {
  items: { id: number; name?: string; board?: number; text?: string; colour?: string | null }[];
  hidden: number;
};

export type Item = {
  id: number;
  number: number;
  name: string;
  group: number;
  position: number;
  values: Record<string, unknown>;
  done: boolean;
  update_count: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};

export type ItemUpdate = {
  id: number;
  author: number | null;
  author_name: string;
  body: string;
  mentions: number[];
  created_at: string;
  edited_at: string | null;
};

export type Activity = {
  id: number;
  item: number;
  item_name: string;
  kind: "created" | "value" | "name" | "moved" | "archived" | "restored" | "update";
  who: string;
  automation_id: number | null;
  column_key: string;
  column_title: string;
  old_text: string;
  new_text: string;
  at: string;
};

export type Template = { key: string; name: string; description: string; columns: string[] };

export type Present = { id: number; name: string; item: number | null; column: string | null };

export type ImportResult = {
  created: number;
  failed: number;
  errors: { row: number; errors: Record<string, unknown> }[];
};
