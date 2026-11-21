import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";

import { useUpdateConnection } from "../api";
import type { Connection, Connector } from "../types";
import { HealthBadge } from "./health-badge";

/**
 * One provider: whether the company is connected, through whose account, and (for Admins) the
 * override between Telejects' account and the company's own.
 */
export function ProviderCard({
  connector,
  connections,
  canManage,
  onConnect,
  onUseOwn,
}: {
  connector: Connector;
  connections: Connection[];
  canManage: boolean;
  onConnect: () => void;
  onUseOwn: (connection: Connection) => void;
}) {
  return (
    <div className="flex flex-col rounded-xl border bg-card p-4">
      <h3 className="font-medium">{connector.name}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{connector.description}</p>

      <div className="mt-3 grid flex-1 content-start gap-2">
        {connections.length ? (
          connections.map((connection) => (
            <ConnectionRow
              key={connection.id}
              connection={connection}
              canManage={canManage}
              onUseOwn={() => onUseOwn(connection)}
            />
          ))
        ) : (
          <p className="text-sm text-muted-foreground">
            Telejects doesn't have an account with {connector.name} for you.
            {canManage ? " Connect your own to use it." : " An Admin can connect your own."}
          </p>
        )}
      </div>

      {canManage && !connections.length && (
        <Button
          className="mt-3 justify-self-start self-start"
          variant="outline"
          onClick={onConnect}
        >
          Connect your account
        </Button>
      )}
    </div>
  );
}

function ConnectionRow({
  connection,
  canManage,
  onUseOwn,
}: {
  connection: Connection;
  canManage: boolean;
  onUseOwn: () => void;
}) {
  const update = useUpdateConnection(connection.id);
  const platform = connection.credentials === "platform";
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <Link
        to="/integrations/$connectionId"
        params={{ connectionId: String(connection.id) }}
        className="flex items-center gap-2 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <div className="grid min-w-0 flex-1 gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <HealthBadge connection={connection} />
            <Badge variant="outline">{platform ? "Telejects account" : "Your account"}</Badge>
          </div>
          <p className="truncate text-xs text-muted-foreground">
            <span className="tabular-nums">{connection.product_count}</span> products
            {connection.health_error ? ` · ${connection.health_error}` : ""}
          </p>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
      </Link>
      {canManage && platform && (
        <Button variant="ghost" size="sm" className="justify-self-start" onClick={onUseOwn}>
          Use your own account
        </Button>
      )}
      {canManage && !platform && connection.can_use_platform && (
        <ConfirmDialog
          title="Use Telejects' account instead?"
          description="Your saved credentials for this provider will be deleted."
          confirmLabel="Use Telejects' account"
          destructive
          onConfirm={() => update.mutate({ credentials: "platform" })}
        >
          <Button
            variant="ghost"
            size="sm"
            className="justify-self-start"
            disabled={update.isPending}
          >
            Use Telejects' account
          </Button>
        </ConfirmDialog>
      )}
    </div>
  );
}
