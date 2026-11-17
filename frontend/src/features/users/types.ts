import type { Permission, RoleRef } from "@/features/auth/types";

export type UserStatus = "invited" | "active";

/** A user of the current company. `id` only means something inside this company. */
export type CompanyUser = {
  id: number;
  email: string;
  name: string;
  role: RoleRef;
  status: UserStatus;
  is_me: boolean;
  joined_at: string;
};

export type Role = RoleRef & {
  description: string;
  is_system: boolean;
  permissions: { code: Permission; label: string }[];
};

export type UserInput = { email: string; name: string; role: number };

export type InvitationInfo = { realm_name: string; email: string; needs_password: boolean };

export type AcceptResult =
  | { signed_in: false; realm_id: number }
  | { signed_in: true; realm_id: number; access: string; refresh: string };
