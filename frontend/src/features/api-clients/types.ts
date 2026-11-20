import type { Permission } from "@/features/auth/types";

/** A company's API client (0006): machine access through OAuth2 client credentials. */
export type ApiClient = {
  id: number;
  name: string;
  client_id: string;
  permissions: Permission[];
  created_by: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  active: boolean;
};

/** Only the answer to creating a client carries its secret. It is never shown again. */
export type CreatedApiClient = ApiClient & { client_secret: string };

export type ApiClientInput = { name: string; permissions: Permission[] };

export type GrantablePermission = { code: Permission; label: string };
