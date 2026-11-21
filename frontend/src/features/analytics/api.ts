import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/network/client";

import type { Dashboard, Portfolio, Source, Widget, WidgetConfig, WidgetData } from "./types";

const ROOT = ["analytics"];
const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export function useDashboards(project: number | null) {
  return useQuery({
    queryKey: [...ROOT, "dashboards", project],
    queryFn: () =>
      api<Dashboard[]>(`/api/analytics/dashboards/${project ? `?project=${project}` : ""}`),
  });
}

export function useWidgetData(id: number, version: string) {
  return useQuery({
    queryKey: [...ROOT, "widget", id, version],
    queryFn: () => api<WidgetData>(`/api/analytics/widgets/${id}/data/`),
    staleTime: 30_000,
  });
}

export function usePreview(project: number | null, config: WidgetConfig) {
  return useQuery({
    queryKey: [...ROOT, "preview", project, config],
    queryFn: () => api<WidgetData>("/api/analytics/preview/", json("POST", { project, config })),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useSources(project: number | null) {
  return useQuery({
    queryKey: [...ROOT, "sources", project],
    queryFn: () => api<Source[]>(`/api/analytics/sources/${project ? `?project=${project}` : ""}`),
  });
}

export function usePortfolio() {
  return useQuery({
    queryKey: [...ROOT, "portfolio"],
    queryFn: () => api<Portfolio>("/api/analytics/portfolio/"),
  });
}

export function useDashboardActions(project: number | null) {
  const client = useQueryClient();
  const refresh = () =>
    void client.invalidateQueries({ queryKey: [...ROOT, "dashboards", project] });
  const onError = (error: Error) => toast.error(error.message);
  return {
    create: useMutation({
      mutationFn: (input: { name: string; starter?: boolean }) =>
        api<Dashboard>("/api/analytics/dashboards/", json("POST", { ...input, project })),
      onSuccess: refresh,
      onError,
    }),
    rename: useMutation({
      mutationFn: ({ id, name }: { id: number; name: string }) =>
        api<Dashboard>(`/api/analytics/dashboards/${id}/`, json("PATCH", { name })),
      onSuccess: refresh,
      onError,
    }),
    remove: useMutation({
      mutationFn: (id: number) =>
        api<null>(`/api/analytics/dashboards/${id}/`, { method: "DELETE" }),
      onSuccess: refresh,
      onError,
    }),
    saveWidget: useMutation({
      mutationFn: ({ id, ...input }: Partial<Widget> & { dashboard?: number }) =>
        id
          ? api<Widget>(`/api/analytics/widgets/${id}/`, json("PATCH", input))
          : api<Widget>("/api/analytics/widgets/", json("POST", input)),
      onSuccess: () => {
        refresh();
        void client.invalidateQueries({ queryKey: [...ROOT, "widget"] });
      },
    }),
    removeWidget: useMutation({
      mutationFn: (id: number) => api<null>(`/api/analytics/widgets/${id}/`, { method: "DELETE" }),
      onSuccess: refresh,
      onError,
    }),
  };
}
