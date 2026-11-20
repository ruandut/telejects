import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/network/client";

import type { ApiClient, ApiClientInput, CreatedApiClient, GrantablePermission } from "./types";

const ROOT = ["api-clients"];

export function useApiClients() {
  return useQuery({ queryKey: ROOT, queryFn: () => api<ApiClient[]>("/api/api-clients/") });
}

/** The permissions I may give a client: my own, with what each lets it do. */
export function useGrantablePermissions() {
  return useQuery({
    queryKey: [...ROOT, "permissions"],
    queryFn: () => api<GrantablePermission[]>("/api/api-clients/permissions/"),
    staleTime: 5 * 60_000,
  });
}

export function useCreateApiClient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ApiClientInput) =>
      api<CreatedApiClient>("/api/api-clients/", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ROOT }),
  });
}

export function useRevokeApiClient() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<ApiClient>(`/api/api-clients/${id}/`, { method: "DELETE" }),
    onSuccess: (revoked) => {
      toast.success(`${revoked.name} revoked. Its tokens stopped working.`);
      void client.invalidateQueries({ queryKey: ROOT });
    },
    onError: (error) => toast.error(error.message),
  });
}
