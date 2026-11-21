/** A permission code from the backend's registry (apps/realms/access_control.py). */
export type Permission =
  | "users.view"
  | "users.manage"
  | "integrations.view"
  | "integrations.manage"
  | "integrations.logs"
  | "feasibilities.view"
  | "feasibilities.run"
  | "feasibilities.quote"
  | "api_clients.manage"
  | "projects.view"
  | "projects.manage";

export type RoleRef = { id: number; key: string; name: string };

export type RealmRef = { id: number; name: string };

export type CurrentRealm = RealmRef & {
  /** My membership's id in this company: how boards name me. */
  membership: number;
  role: RoleRef;
  /** What I may do in this company. The app shows and hides things by these. */
  permissions: Permission[];
};

export type Me = {
  id: number;
  email: string;
  name: string;
  /** Telejects' own staff, who keep platform data such as the price book. */
  is_staff: boolean;
  /** The company this tab's requests work in; null when I have none (or lost access). */
  realm: CurrentRealm | null;
  realms: RealmRef[];
};
