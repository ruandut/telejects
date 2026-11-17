import { useMe } from "@/features/auth/api";
import type { Permission } from "@/features/auth/types";

/**
 * Whether I may do `code` in the tab's company. For showing and hiding things only: the server
 * checks every request itself. Never check a role's name or key instead.
 */
export function usePermission(code: Permission): boolean {
  return useMe().data?.realm?.permissions.includes(code) ?? false;
}
