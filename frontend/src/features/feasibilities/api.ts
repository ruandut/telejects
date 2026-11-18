import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useLive } from "@/features/realms/live";
import { api, apiFile } from "@/network/client";

import type { Run, RunProduct, Site, SitePage, StartRunInput } from "./types";

const ROOT = ["feasibilities"];
const runPath = (id: number) => `/api/feasibilities/runs/${id}/`;

export type SiteFilters = { page: number; pageSize: number; state: string; search: string };

export function useRuns() {
  const client = useQueryClient();
  useLive(
    "feasibility_runs",
    null,
    () => void client.invalidateQueries({ queryKey: [...ROOT, "runs"], exact: true }),
  );
  return useQuery({
    queryKey: [...ROOT, "runs"],
    queryFn: () => api<Run[]>("/api/feasibilities/runs/"),
  });
}

export function useRun(id: number) {
  return useQuery({ queryKey: [...ROOT, "run", id], queryFn: () => api<Run>(runPath(id)) });
}

export function useRunSites(id: number, filters: SiteFilters) {
  return useQuery({
    queryKey: [...ROOT, "run", id, "sites", filters],
    queryFn: () => {
      const params = new URLSearchParams({
        page: String(filters.page),
        page_size: String(filters.pageSize),
      });
      if (filters.state) params.set("state", filters.state);
      if (filters.search) params.set("search", filters.search);
      return api<SitePage>(`${runPath(id)}sites/?${params}`);
    },
    placeholderData: (previous) => previous,
  });
}

/** Put lines that just finished into every cached page of this run that shows them. */
function patchSites(client: QueryClient, runId: number, sites: Site[]) {
  const byId = new Map(sites.map((site) => [site.id, site]));
  client.setQueriesData<SitePage>({ queryKey: [...ROOT, "run", runId, "sites"] }, (page) =>
    page ? { ...page, results: page.results.map((site) => byId.get(site.id) ?? site) } : page,
  );
}

/**
 * Each line's results arrive over the socket as they finish, built by the server with the same
 * serializers as the API, and go straight into the cache. After a reconnect (or when the server
 * only says "changed"), everything shown is fetched again.
 */
export function useRunLive(runId: number) {
  const client = useQueryClient();
  useLive("feasibility_run", runId, (message) => {
    if (message.type === "data") {
      const { run, sites } = message.data as { run: Run; sites: Site[] };
      client.setQueryData([...ROOT, "run", runId], run);
      patchSites(client, runId, sites);
    } else if (message.type === "changed" || message.type === "reconnected") {
      void client.invalidateQueries({ queryKey: [...ROOT, "run", runId] });
    }
  });
}

export function useRunProducts() {
  return useQuery({
    queryKey: [...ROOT, "products"],
    queryFn: () => api<RunProduct[]>("/api/feasibilities/runs/products/"),
  });
}

export function useStartRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: StartRunInput) =>
      api<Run>("/api/feasibilities/runs/", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (run) => {
      toast.success(`${run.name} started`);
      void client.invalidateQueries({ queryKey: [...ROOT, "runs"] });
    },
  });
}

export function useRunAction(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: "cancel" | "retry-failed") =>
      api<Run>(`${runPath(id)}${action}/`, { method: "POST" }),
    onSuccess: (run, action) => {
      toast.success(action === "cancel" ? "Run cancelled" : "Retrying what failed…");
      client.setQueryData([...ROOT, "run", id], run);
      void client.invalidateQueries({ queryKey: [...ROOT, "run", id, "sites"] });
    },
    onError: (error) => toast.error(error.message),
  });
}

export function useExportRun(id: number) {
  return useMutation({
    mutationFn: () => apiFile(`${runPath(id)}export/`),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (error) => toast.error(error.message),
  });
}
