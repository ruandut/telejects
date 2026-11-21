import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api, apiFile } from "@/network/client";

import type {
  BookConnectProduct,
  BookOptions,
  ConnectProductInput,
  PriceDefinition,
  PriceDefinitionInput,
  PriceFilters,
  PricePage,
} from "./types";

const ROOT = ["price-book"];
const BASE = "/api/price-book";
export const PAGE_SIZE = 100;

export function usePrices(filters: PriceFilters) {
  const params = new URLSearchParams({ page: String(filters.page), page_size: String(PAGE_SIZE) });
  if (filters.search) params.set("search_string", filters.search);
  if (filters.provider !== null) params.set("provider", String(filters.provider));
  if (filters.medium) params.set("medium", filters.medium);
  return useQuery({
    queryKey: [...ROOT, "prices", filters],
    queryFn: () => api<PricePage>(`${BASE}/definitions/?${params}`),
    placeholderData: keepPreviousData,
  });
}

export function useBookOptions() {
  return useQuery({
    queryKey: [...ROOT, "options"],
    queryFn: () => api<BookOptions>(`${BASE}/options/`),
    staleTime: 5 * 60_000,
  });
}

export function useBookConnectProducts() {
  return useQuery({
    queryKey: [...ROOT, "connect-products"],
    queryFn: () => api<BookConnectProduct[]>(`${BASE}/connect-products/`),
  });
}

/** Everything on the page may change after an edit: prices, counts and the options. */
function useRefresh() {
  const client = useQueryClient();
  return () => void client.invalidateQueries({ queryKey: ROOT });
}

export function useSavePrice(id: number | null) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: PriceDefinitionInput) =>
      api<PriceDefinition>(id ? `${BASE}/definitions/${id}/` : `${BASE}/definitions/`, {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (saved) => {
      toast.success(id ? `${saved.name} saved` : `${saved.name} added`);
      refresh();
    },
  });
}

export function useDeletePrice() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (price: PriceDefinition) =>
      api<null>(`${BASE}/definitions/${price.id}/`, { method: "DELETE" }),
    onSuccess: (_, price) => {
      toast.success(`${price.name} deleted`);
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });
}

export function useSaveConnectProduct(id: number | null) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: ConnectProductInput) =>
      api<BookConnectProduct>(
        id ? `${BASE}/connect-products/${id}/` : `${BASE}/connect-products/`,
        { method: id ? "PUT" : "POST", body: JSON.stringify(input) },
      ),
    onSuccess: (saved) => {
      toast.success(id ? `${saved.name} saved` : `${saved.name} added`);
      refresh();
    },
  });
}

export function useDeleteConnectProduct() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (product: BookConnectProduct) =>
      api<null>(`${BASE}/connect-products/${product.id}/`, { method: "DELETE" }),
    onSuccess: (_, product) => {
      toast.success(`${product.name} deleted`);
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });
}

/** Rapid's price book downloads, as CSV or PDF. */
export function useDownloadBook() {
  return useMutation({
    mutationFn: (kind: "csv" | "pdf") => apiFile(`${BASE}/export/${kind}/`),
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
