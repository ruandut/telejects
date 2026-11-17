import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";

import { NoAccess } from "@/components/no-access";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useConnections, useConnectors, useIntegrationsLive } from "@/features/integrations/api";
import { ConnectDialog } from "@/features/integrations/components/connect-dialog";
import { OwnAccountDialog } from "@/features/integrations/components/own-account-dialog";
import { ProviderCard } from "@/features/integrations/components/provider-card";
import type { Connection, Connector } from "@/features/integrations/types";
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
  const [override, setOverride] = useState<{ connector: Connector; connection: Connection } | null>(
    null,
  );

  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        The providers your feasibility runs use. They work through Telejects' accounts from the
        start; an Admin can use your company's own account for any of them instead.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {connectors.data && connections.data ? (
          connectors.data.map((connector) => (
            <ProviderCard
              key={connector.key}
              connector={connector}
              connections={connections.data.filter((c) => c.connector_key === connector.key)}
              canManage={canManage}
              onConnect={() => setConnecting(connector)}
              onUseOwn={(connection) => setOverride({ connector, connection })}
            />
          ))
        ) : connectors.error || connections.error ? (
          <p role="alert" className="text-sm text-destructive">
            {(connectors.error ?? connections.error)?.message}
          </p>
        ) : (
          <>
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </>
        )}
      </div>

      {connecting && <ConnectDialog connector={connecting} onClose={() => setConnecting(null)} />}
      {override && (
        <OwnAccountDialog
          connector={override.connector}
          connection={override.connection}
          onClose={() => setOverride(null)}
        />
      )}
    </div>
  );
}
