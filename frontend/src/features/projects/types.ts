export type Level = "view" | "edit" | "manage";

export type ProjectStatus = "planning" | "active" | "on_hold" | "done" | "archived";

export type Project = {
  id: number;
  name: string;
  client: string;
  description: string;
  status: ProjectStatus;
  colour: string;
  owner: number | null;
  owner_name: string | null;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
  updated_at: string;
  my_level: Level;
};

export type ProjectInput = Partial<
  Pick<
    Project,
    "name" | "client" | "description" | "status" | "colour" | "start_date" | "end_date" | "owner"
  >
> & { template?: string };

export type Person = { id: number; name: string; email: string };

export type ProjectMember = { id: number; person: Person; level: Level; added_at: string };

export type PersonAccess = {
  manages_all: boolean;
  projects: { project: number; name: string; level: Level }[];
};

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  planning: "Planning",
  active: "Active",
  on_hold: "On hold",
  done: "Done",
  archived: "Archived",
};

export const STATUS_COLOURS: Record<ProjectStatus, string> = {
  planning: "blue",
  active: "green",
  on_hold: "amber",
  done: "purple",
  archived: "grey",
};

export const LEVEL_LABELS: Record<Level, string> = {
  view: "Can view",
  edit: "Can edit",
  manage: "Can manage",
};

export const LEVEL_HINTS: Record<Level, string> = {
  view: "Sees boards, dashboards and updates",
  edit: "Also changes items and writes updates",
  manage: "Also columns, groups, views, automations, dashboards and access",
};

export function atLeast(level: Level | null | undefined, needed: Level): boolean {
  const rank = { view: 1, edit: 2, manage: 3 };
  return !!level && rank[level] >= rank[needed];
}
