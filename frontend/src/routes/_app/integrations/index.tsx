import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, Plug } from "lucide-react";
import { useState } from "react";

import { NoAccess } from "@/components/no-access";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useConnections, useConnectors, useIntegrationsLive } from "@/features/integrations/api";
import { ConnectDialog } from "@/features/integrations/components/connect-dialog";
import { HealthBadge } from "@/features/integrations/components/health-badge";
import type { Connector } from "@/features/integrations/types";
import { usePermission } from "@/features/realms/permissions";

export const Route = createFileRoute("/_app/integrations/")({
  component: IntegrationsPage,
});

function IntegrationsPage() {
  const me = useMe();
  const canView = usePermission("integrations.view");
  if (me.data && !canView) return <NoAccess section="Integrations" />;
  return <Integrations />;
}

function Integrations() {
  useIntegrationsLive();
  const canManage = usePermission("integrations.manage");
  const connectors = useConnectors();
  const connections = useConnections();
  const [connecting, setConnecting] = useState<Connector | null>(null);

  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        Connect your company's own provider accounts. Feasibility runs use the products they offer.
      </p>

      <section className="mt-8">
        <h2 className="font-semibold">Your connections</h2>
        <div className="mt-3">
          {connections.data ? (
            connections.data.length ? (
              <ul className="grid gap-2">
                {connections.data.map((connection) => (
                  <li key={connection.id}>
                    <Link
                      to="/integrations/$connectionId"
                      params={{ connectionId: String(connection.id) }}
                      className="flex items-center gap-3 rounded-xl border bg-card p-4 outline-none hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                        <Plug className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="truncate font-medium">{connection.name}</span>
                          <HealthBadge connection={connection} />
                        </div>
                        <p className="truncate text-sm text-muted-foreground">
                          {connection.connector_name} ·{" "}
                          <span className="tabular-nums">{connection.product_count}</span> products
                          {connection.health_error ? ` · ${connection.health_error}` : ""}
                        </p>
                      </div>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
                No providers connected yet.
              </p>
            )
          ) : connections.error ? (
            <p role="alert" className="text-sm text-destructive">
              {connections.error.message}
            </p>
          ) : (
            <Skeleton className="h-16 w-full" />
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-semibold">Available providers</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {connectors.data?.map((connector) => (
            <div key={connector.key} className="flex flex-col rounded-xl border bg-card p-4">
              <h3 className="font-medium">{connector.name}</h3>
              <p className="mt-1 flex-1 text-sm text-muted-foreground">{connector.description}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                {connector.capabilities
                  .map((c) => (c === "feasibility" ? "Feasibility" : c))
                  .join(", ")}
              </p>
              {canManage && (
                <Button
                  className="mt-3 self-start"
                  variant="outline"
                  onClick={() => setConnecting(connector)}
                >
                  Connect
                </Button>
              )}
            </div>
          )) ?? <Skeleton className="h-32 w-full" />}
        </div>
      </section>

      {connecting && <ConnectDialog connector={connecting} onClose={() => setConnecting(null)} />}
    </div>
  );
}
