import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useLive } from "@/features/realms/live";
import { api } from "@/network/client";

import type { Connection, Connector, ProviderProduct, SyncRun } from "./types";

const ROOT = ["integrations"];
const connectionPath = (id: number) => `/api/integrations/connections/${id}/`;

/** Keep integrations fresh while a page shows them: the socket says when they change. */
export function useIntegrationsLive() {
  const client = useQueryClient();
  useLive("integrations", null, () => void client.invalidateQueries({ queryKey: ROOT }));
}

export function useConnectors() {
  return useQuery({
    queryKey: [...ROOT, "connectors"],
    queryFn: () => api<Connector[]>("/api/integrations/connectors/"),
    staleTime: 5 * 60_000,
  });
}

export function useConnections() {
  return useQuery({
    queryKey: [...ROOT, "connections"],
    queryFn: () => api<Connection[]>("/api/integrations/connections/"),
  });
}

export function useConnection(id: number) {
  return useQuery({
    queryKey: [...ROOT, "connections", id],
    queryFn: () => api<Connection>(connectionPath(id)),
  });
}

export function useConnectionProducts(id: number) {
  return useQuery({
    queryKey: [...ROOT, "connections", id, "products"],
    queryFn: () => api<ProviderProduct[]>(`${connectionPath(id)}products/`),
  });
}

export function useConnectionSyncs(id: number) {
  return useQuery({
    queryKey: [...ROOT, "connections", id, "syncs"],
    queryFn: () => api<SyncRun[]>(`${connectionPath(id)}syncs/`),
  });
}

export type ConnectInput = { connector: string; name: string; fields: Record<string, string> };

export function useConnect() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ConnectInput) =>
      api<Connection>("/api/integrations/connections/", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (connection) => {
      toast.success(`${connection.name} connected. Testing it and fetching its products…`);
      void client.invalidateQueries({ queryKey: ROOT });
    },
  });
}

export function useUpdateConnection(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (changes: { name?: string; fields?: Record<string, string>; enabled?: boolean }) =>
      api<Connection>(connectionPath(id), { method: "PATCH", body: JSON.stringify(changes) }),
    onSuccess: (connection) => {
      toast.success(`${connection.name} saved`);
      void client.invalidateQueries({ queryKey: ROOT });
    },
  });
}

export function useRemoveConnection(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ deleted: false; detail: string } | null>(connectionPath(id), { method: "DELETE" }),
    onSuccess: (result) => {
      toast.success(result ? result.detail : "Connection removed");
      void client.invalidateQueries({ queryKey: ROOT });
    },
  });
}

export function useConnectionAction(id: number) {
  return useMutation({
    mutationFn: (action: "test" | "sync") =>
      api(`${connectionPath(id)}${action}/`, { method: "POST" }),
    onSuccess: (_data, action) =>
      toast.success(action === "test" ? "Testing the connection…" : "Fetching products…"),
    onError: (error) => toast.error(error.message),
  });
}
