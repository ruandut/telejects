import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { NoAccess } from "@/components/no-access";
import { SettingsSection } from "@/components/settings-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import {
  useConnection,
  useConnectionAction,
  useConnectionProducts,
  useConnectionSyncs,
  useConnectors,
  useIntegrationsLive,
  useRemoveConnection,
  useUpdateConnection,
} from "@/features/integrations/api";
import { ConnectionForm } from "@/features/integrations/components/connection-form";
import { HealthBadge } from "@/features/integrations/components/health-badge";
import type { Connection, ProviderProduct } from "@/features/integrations/types";
import { usePermission } from "@/features/realms/permissions";
import { ApiError } from "@/network/errors";

export const Route = createFileRoute("/_app/integrations/$connectionId")({
  component: ConnectionPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short" });

function ConnectionPage() {
  const me = useMe();
  const canView = usePermission("integrations.view");
  const id = Number(Route.useParams().connectionId);
  if (me.data && !canView) return <NoAccess section="Integrations" />;
  return <ConnectionDetail id={id} />;
}

function ConnectionDetail({ id }: { id: number }) {
  useIntegrationsLive();
  const connection = useConnection(id);
  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 p-4 md:p-8">
      <Link
        to="/integrations"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Integrations
      </Link>
      {connection.data ? (
        <Loaded connection={connection.data} />
      ) : connection.error ? (
        <p role="alert" className="text-sm text-destructive">
          {connection.error instanceof ApiError && connection.error.status === 404
            ? "There's no such connection."
            : connection.error.message}
        </p>
      ) : (
        <Skeleton className="h-40 w-full" />
      )}
    </div>
  );
}

function Loaded({ connection }: { connection: Connection }) {
  const canManage = usePermission("integrations.manage");
  const connectors = useConnectors();
  const connector = connectors.data?.find((c) => c.key === connection.connector_key);
  const update = useUpdateConnection(connection.id);
  const action = useConnectionAction(connection.id);
  const remove = useRemoveConnection(connection.id);
  const navigate = useNavigate();

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{connection.name}</h1>
            <HealthBadge connection={connection} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {connection.connector_name}
            {connection.health_checked_at &&
              ` · checked ${when.format(new Date(connection.health_checked_at))}`}
          </p>
          {connection.health_error && (
            <p className="mt-1 text-sm text-destructive">{connection.health_error}</p>
          )}
        </div>
        {canManage && connection.enabled && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate("test")}
            >
              <ShieldCheck /> Test connection
            </Button>
            <Button
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate("sync")}
            >
              <RefreshCw /> Sync products
            </Button>
          </div>
        )}
      </div>

      {canManage && connector && (
        <SettingsSection
          title="Settings"
          description={`What ${connector.name} needs. Changing the credentials tests them again.`}
        >
          <ConnectionForm
            key={connection.id}
            connector={connector}
            connection={connection}
            pending={update.isPending}
            error={update.error}
            submitLabel="Save"
            onSubmit={(name, fields) =>
              update.mutate({
                name,
                fields: Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== "")),
              })
            }
          />
          <div className="mt-6 flex flex-wrap gap-2 border-t pt-4">
            <Button
              variant="outline"
              onClick={() => update.mutate({ enabled: !connection.enabled })}
              disabled={update.isPending}
            >
              {connection.enabled ? "Turn off" : "Turn on"}
            </Button>
            <Button
              variant="outline"
              className="text-destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (
                  !window.confirm(
                    `Remove ${connection.name}? Runs that used it keep their results.`,
                  )
                )
                  return;
                remove.mutate(undefined, {
                  onSuccess: (result) => {
                    if (!result) void navigate({ to: "/integrations" });
                  },
                });
              }}
            >
              <Trash2 /> Remove
            </Button>
          </div>
        </SettingsSection>
      )}

      <Products id={connection.id} />
      <Syncs id={connection.id} />
    </>
  );
}

function Products({ id }: { id: number }) {
  const products = useConnectionProducts(id);
  const groups = useMemo(() => {
    const byType = new Map<string, ProviderProduct[]>();
    for (const product of products.data ?? []) {
      const list = byType.get(product.product_type_label) ?? [];
      list.push(product);
      byType.set(product.product_type_label, list);
    }
    return [...byType.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [products.data]);

  return (
    <SettingsSection title="Products" description="What this provider offers, grouped by type.">
      {!products.data ? (
        <Skeleton className="h-20 w-full" />
      ) : groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">No products yet.</p>
      ) : (
        <div className="grid gap-4">
          {groups.map(([label, list]) => (
            <div key={label}>
              <h3 className="text-sm font-medium">{label}</h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {list.map((product) => (
                  <li key={product.id}>
                    <Badge
                      variant={product.retired_at ? "outline" : "secondary"}
                      className="max-w-full"
                    >
                      <span className="truncate">{product.name}</span>
                      {product.retired_at && " (retired)"}
                    </Badge>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </SettingsSection>
  );
}

const KIND = { sync_products: "Product sync", test_connection: "Connection test" };
const TRIGGER = { connect: "on connecting", manual: "by hand", scheduled: "scheduled" };

function Syncs({ id }: { id: number }) {
  const syncs = useConnectionSyncs(id);
  return (
    <SettingsSection title="History" description="Recent tests and product syncs.">
      {!syncs.data ? (
        <Skeleton className="h-20 w-full" />
      ) : syncs.data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing yet.</p>
      ) : (
        <ul className="divide-y text-sm">
          {syncs.data.map((sync) => (
            <li
              key={sync.id}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2"
            >
              <span>
                <span className="font-medium">{KIND[sync.kind]}</span>{" "}
                <span className="text-muted-foreground">{TRIGGER[sync.trigger]}</span>
              </span>
              <span className="tabular-nums text-muted-foreground">
                {when.format(new Date(sync.started_at))}
              </span>
              <span className="basis-full text-muted-foreground">
                {sync.outcome === "running" ? (
                  "Running…"
                ) : sync.outcome === "failed" ? (
                  <span className="text-destructive">{sync.error}</span>
                ) : sync.kind === "sync_products" ? (
                  `${sync.added} added, ${sync.retired} retired`
                ) : (
                  "Credentials accepted"
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </SettingsSection>
  );
}
