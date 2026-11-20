export type LogOperation = "check_feasibility" | "sync_products" | "test_connection";

/** One request to a provider and its answer, secrets redacted. */
export type LogEntry = {
  id: number;
  created_at: string;
  operation: LogOperation;
  operation_label: string;
  connection_id: number | null;
  connection_name: string;
  credentials: "own" | "platform" | "";
  method: string;
  url: string;
  status_code: number | null;
  duration_ms: number | null;
  /** "ok", or the kind of error (timeout, provider_down, auth, ...). */
  outcome: string;
  error: string;
  attempt: number;
  run_id: number | null;
  check_id: number | null;
  sync_id: number | null;
  site_check_id: number | null;
};

export type LogDetail = LogEntry & {
  connector_key: string;
  definition_version: number | null;
  request_headers: Record<string, string>;
  request_body: string;
  response_headers: Record<string, string>;
  response_body: string;
};

export type LogPage = { count: number; page: number; page_size: number; results: LogEntry[] };

export type LogLimits = { max_entries: number; default: number; kept: number };

export type LogFilters = {
  page: number;
  search: string;
  connection: string;
  operation: string;
  outcome: string;
  status: string;
  run: string;
  from: string;
  to: string;
};

export const NO_FILTERS: LogFilters = {
  page: 1,
  search: "",
  connection: "",
  operation: "",
  outcome: "",
  status: "",
  run: "",
  from: "",
  to: "",
};
