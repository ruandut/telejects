export type Trigger =
  | { type: "item_created" }
  | { type: "column_changed"; column: string | null }
  | { type: "status_changed"; column: string; to: string[] }
  | { type: "item_moved"; group: number | null }
  | {
      type: "date_arrives";
      column: string;
      when: "before" | "on" | "after";
      days: number;
      time: string;
    }
  | {
      type: "schedule";
      every: "day" | "weekday" | "week" | "month";
      weekday?: number;
      day?: number;
      time: string;
    };

export type Condition = { column: string; op: string; value: unknown };

export type Action =
  | { type: "set_value"; column: string; value: unknown }
  | { type: "clear_value"; column: string }
  | { type: "copy_value"; from: string; to: string }
  | { type: "increment"; column: string; by: string | number }
  | { type: "move_to_group"; group: number }
  | {
      type: "notify";
      people_column: string | null;
      members: number[];
      trigger_person: boolean;
      message: string;
    }
  | {
      type: "create_item";
      board: number;
      group: number | null;
      name: string;
      copy: { from: string; to: string }[];
      link_column: string | null;
    }
  | { type: "archive_item" };

export type Delay = { amount: number; unit: "minutes" | "hours" | "days" } | null;

export type Automation = {
  id: number;
  board: number;
  name: string;
  enabled: boolean;
  trigger: Trigger;
  conditions: Condition[];
  actions: Action[];
  delay: Delay;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  run_count: number;
  last_run_at: string | null;
};

export type AutomationInput = Pick<
  Automation,
  "name" | "trigger" | "conditions" | "actions" | "delay"
> & { enabled?: boolean };

export type Run = {
  id: number;
  item: number | null;
  item_name: string;
  status: "done" | "failed" | "skipped" | "scheduled" | "cancelled";
  message: string;
  due_at: string | null;
  created_at: string;
  finished_at: string | null;
};
