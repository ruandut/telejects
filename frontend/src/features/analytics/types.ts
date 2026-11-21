export type WidgetKind = "bar" | "stacked" | "line" | "area" | "pie" | "number" | "table";

export type GroupBy = {
  by: "none" | "column" | "group" | "board" | "project" | "created" | "completed" | "done";
  column?: string;
};

export type WidgetConfig = {
  boards?: number[];
  metric?: { op: "count" | "sum" | "avg" | "min" | "max"; column?: string };
  group_by?: GroupBy;
  series_by?: GroupBy | null;
  bucket?: "day" | "week" | "month" | "quarter" | "year";
  filters?: { column: string; op: string; value: unknown }[];
  limit?: number;
};

export type Widget = {
  id: number;
  dashboard: number;
  title: string;
  kind: WidgetKind;
  config: WidgetConfig;
  position: number;
  width: number;
};

export type Dashboard = {
  id: number;
  project: number | null;
  name: string;
  position: number;
  widgets: Widget[];
  created_at: string;
};

export type WidgetData = {
  labels: string[];
  colours: (string | null)[];
  series: { key: string; name: string; colour: string | null; data: (number | null)[] }[];
  total: number | null;
  items: number;
};

export type Source = {
  id: number;
  name: string;
  project: { id: number; name: string };
  groups: { id: number; name: string }[];
  columns: { key: string; title: string; type: string; labels: string[] }[];
};

export type PortfolioProject = {
  id: number;
  name: string;
  client: string;
  colour: string;
  status: string;
  my_level: string;
  owner_name: string | null;
  end_date: string | null;
  boards: number;
  items: number;
  done: number;
  overdue: number;
  next_due: string | null;
  progress: number;
  by_status: { label: string; colour: string; count: number }[];
};

export type Portfolio = {
  totals: { projects: number; items: number; done: number; overdue: number };
  projects: PortfolioProject[];
  weeks: string[];
  created: number[];
  completed: number[];
  recent: {
    id: number;
    who: string;
    kind: string;
    item: number;
    item_name: string;
    board: number;
    project: number;
    column_title: string;
    old_text: string;
    new_text: string;
    at: string;
  }[];
};
