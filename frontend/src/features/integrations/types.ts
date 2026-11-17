export type ConnectorField = {
  key: string;
  label: string;
  help: string;
  type: "text" | "email" | "secret";
  required: boolean;
};

/** A provider the company can connect, as its connector definition describes it. */
export type Connector = {
  key: string;
  /** The company may use Telejects' own account for this provider (granted by staff). */
  included: boolean;
  name: string;
  description: string;
  capabilities: string[];
  version: number;
  fields: ConnectorField[];
};

export type SyncRun = {
  id: number;
  kind: "sync_products" | "test_connection";
  trigger: "connect" | "manual" | "scheduled";
  outcome: "running" | "ok" | "failed";
  started_at: string;
  finished_at: string | null;
  added: number;
  retired: number;
  error: string;
  /** The sync's last log entry, while the log still keeps it. */
  log: number | null;
};

export type Health = "unknown" | "ok" | "failing";

/** The company's own account with a provider. Secrets never come back: only which are set. */
export type Connection = {
  id: number;
  name: string;
  connector_key: string;
  connector_name: string;
  /** "platform": through Telejects' account, whose settings and secrets are never shown. */
  credentials: "own" | "platform";
  /** Telejects' account is granted for this provider, so the connection can switch to it. */
  can_use_platform: boolean;
  settings: Record<string, string>;
  secrets_set: string[];
  enabled: boolean;
  health: Health;
  health_error: string;
  health_checked_at: string | null;
  product_count: number;
  last_sync: SyncRun | null;
  created_at: string;
};

export type ProductType =
  | "fibre"
  | "fixed_wireless"
  | "lte"
  | "5g"
  | "microwave"
  | "satellite"
  | "other";

export type ProviderProduct = {
  id: number;
  connection: number;
  connection_name: string;
  code: string;
  name: string;
  product_type: ProductType;
  product_type_label: string;
  retired_at: string | null;
};
