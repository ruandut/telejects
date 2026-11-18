import type { ProductType } from "@/features/integrations/types";

export type RunStatus = "queued" | "running" | "completed" | "cancelled";

export type RunProduct = {
  id: number;
  name: string;
  code: string;
  product_type: ProductType;
  connection: number;
  connection_name: string;
  retired_at: string | null;
};

export type Run = {
  id: number;
  name: string;
  status: RunStatus;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  site_count: number;
  sites_finished: number;
  checks_total: number;
  checks_done: number;
  checks_failed: number;
  checks_cancelled: number;
  columns?: string[];
  mapping?: Record<string, string>;
  products: RunProduct[];
};

export type ResultStatus = "available" | "near_net" | "coverage_only" | "not_available";

export type SiteResult = {
  product: number;
  status: ResultStatus;
  status_label: string;
  variant_name: string;
  product_type: ProductType;
  product_type_label: string;
  bandwidths: [number | null, number | null][];
  note: string;
};

export type SiteState = "pending" | "done" | "error" | "cancelled";

export type Site = {
  id: number;
  line_number: number;
  name: string;
  latitude: number;
  longitude: number;
  state: SiteState;
  results: SiteResult[];
  /** Failed provider calls; `log` is the call's log entry while the log still keeps it. */
  errors: { connection: number; connection_name: string; message: string; log: number | null }[];
};

export type SitePage = {
  count: number;
  page: number;
  page_size: number;
  next: string | null;
  previous: string | null;
  results: Site[];
};

export type RowInput = {
  line_number: number;
  name: string;
  latitude: string;
  longitude: string;
  row: Record<string, string>;
};

export type StartRunInput = {
  name: string;
  products: number[];
  rows: RowInput[];
  columns: string[];
  mapping: Record<string, string>;
};
