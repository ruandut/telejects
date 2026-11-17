import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, publicApi } from "@/network/client";
import { queryClient } from "@/network/query-client";
import { useAuth } from "@/stores/auth";
import { useRealm } from "@/stores/realm";

import type { AcceptResult, CompanyUser, InvitationInfo, Role, UserInput } from "./types";

const USERS = ["users"];

export function useUsers() {
  return useQuery({ queryKey: USERS, queryFn: () => api<CompanyUser[]>("/api/users/") });
}

export function useRoles() {
  return useQuery({
    queryKey: ["users", "roles"],
    queryFn: () => api<Role[]>("/api/roles/"),
    staleTime: 5 * 60_000,
  });
}

const nameOf = (user: CompanyUser) => user.name || user.email;

export function useAddUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: UserInput) =>
      api<CompanyUser>("/api/users/", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (user) => {
      toast.success(`Invitation sent to ${user.email}`);
      void client.invalidateQueries({ queryKey: USERS });
    },
  });
}

export function useUpdateUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: number; name?: string; role?: number }) =>
      api<CompanyUser>(`/api/users/${id}/`, { method: "PATCH", body: JSON.stringify(changes) }),
    onSuccess: (user) => {
      toast.success(`${nameOf(user)} updated`);
      // My own role or name may have changed, which /me also reports.
      void client.invalidateQueries();
    },
  });
}

export function useRemoveUser() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ user, newAdmin }: { user: CompanyUser; newAdmin: number | null }) =>
      api(`/api/users/${user.id}/`, {
        method: "DELETE",
        body: JSON.stringify(newAdmin === null ? {} : { new_admin: newAdmin }),
      }),
    onSuccess: (_data, { user }) => {
      toast.success(
        user.status === "invited"
          ? `Invitation for ${user.email} cancelled`
          : `${nameOf(user)} removed`,
      );
      // Removing myself ends my access: everything cached is stale, and /me decides what's next.
      void client.invalidateQueries();
    },
  });
}

export function useResendInvitation() {
  return useMutation({
    mutationFn: (user: CompanyUser) => api(`/api/users/${user.id}/resend/`, { method: "POST" }),
    onSuccess: (_data, user) => toast.success(`New invitation sent to ${user.email}`),
    onError: (error) => toast.error(error.message),
  });
}

// --- confirming an account by its emailed link (signed out) -----------------------------------

const invitationPath = (token: string) => `/api/users/invitations/${encodeURIComponent(token)}/`;

export function useInvitation(token: string) {
  return useQuery({
    queryKey: ["invitation", token],
    queryFn: () => publicApi<InvitationInfo>(invitationPath(token)),
    retry: false,
    staleTime: Infinity,
  });
}

export function useAcceptInvitation(token: string) {
  return useMutation({
    mutationFn: (password: string | null) =>
      publicApi<AcceptResult>(invitationPath(token), {
        method: "POST",
        body: JSON.stringify(password === null ? {} : { password }),
      }),
    onSuccess: (result) => {
      if (!result.signed_in) return;
      // Whoever was signed in on this browser before, this is now the confirmed account, in the
      // company that invited them.
      queryClient.clear();
      useRealm.getState().setRealmId(result.realm_id);
      useAuth.getState().setTokens(result);
    },
  });
}
