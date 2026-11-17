import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { useLive } from "@/features/realms/live";
import { api } from "@/network/client";

import type { LogDetail, LogEntry, LogFilters, LogLimits, LogPage } from "./types";
import { NO_FILTERS } from "./types";

const ROOT = ["integration-logs"];

const isUnfiltered = (filters: LogFilters) =>
  Object.entries(filters).every(([key, value]) =>
    key === "page" ? value === 1 : value === NO_FILTERS[key as keyof LogFilters],
  );

export function useLogs(filters: LogFilters) {
  const client = useQueryClient();
  const key = [...ROOT, "list", filters];
  // New entries arrive over the socket. On the first, unfiltered page they go straight on top;
  // anywhere else the list is fetched again, as the server decides what matches a filter.
  useLive("integration_logs", null, (message) => {
    void client.invalidateQueries({ queryKey: [...ROOT, "limits"] });
    if (message.type === "data" && isUnfiltered(filters)) {
      const { entries } = message.data as { entries: LogEntry[] };
      client.setQueryData<LogPage>(key, (page) => {
        if (!page) return page;
        const known = new Set(page.results.map((e) => e.id));
        const fresh = entries.filter((e) => !known.has(e.id));
        return {
          ...page,
          count: page.count + fresh.length,
          results: [...fresh, ...page.results].slice(0, page.page_size),
        };
      });
    } else {
      void client.invalidateQueries({ queryKey: [...ROOT, "list"] });
    }
  });
  return useQuery({
    queryKey: key,
    queryFn: () => {
      const params = new URLSearchParams();
      for (const [name, value] of Object.entries(filters)) {
        if (value !== "" && !(name === "page" && value === 1)) params.set(name, String(value));
      }
      return api<LogPage>(`/api/integration-logs/?${params}`);
    },
    placeholderData: keepPreviousData,
  });
}

export function useLog(id: number) {
  return useQuery({
    queryKey: [...ROOT, "entry", id],
    queryFn: () => api<LogDetail>(`/api/integration-logs/${id}/`),
    retry: false,
  });
}

export function useLogLimits() {
  return useQuery({
    queryKey: [...ROOT, "limits"],
    queryFn: () => api<LogLimits>("/api/integration-logs/limits/"),
  });
}
