import { createFileRoute } from "@tanstack/react-router";
import { ExternalLink, KeyRound, Plus } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { NoAccess } from "@/components/no-access";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiClients, useRevokeApiClient } from "@/features/api-clients/api";
import { CreateClientDialog } from "@/features/api-clients/components/create-client-dialog";
import { API_DOCS_URL } from "@/features/api-clients/docs";
import type { ApiClient } from "@/features/api-clients/types";
import { useMe } from "@/features/auth/api";
import { usePermission } from "@/features/realms/permissions";

export const Route = createFileRoute("/_app/developers/credentials")({
  component: ServerCredentialsPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "short" });
const date = (value: string | null) => (value ? when.format(new Date(value)) : "Never");

function ServerCredentialsPage() {
  const me = useMe();
  const canManage = usePermission("api_clients.manage");
  if (me.data && !canManage) return <NoAccess section="server credentials" />;
  return <ApiClients companyName={me.data?.realm?.name} />;
}

function ApiClients({ companyName }: { companyName: string | undefined }) {
  const clients = useApiClients();
  const [creating, setCreating] = useState(false);
  const active = (clients.data ?? []).filter((c) => c.active);
  const revoked = (clients.data ?? []).filter((c) => !c.active);

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">Server credentials</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            One for each system that uses {companyName ?? "your company"}'s feasibilities and quotes
            directly.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus /> New credentials
        </Button>
      </div>

      <div className="mt-6 grid gap-3">
        {clients.data ? (
          active.length ? (
            active.map((client) => <ClientCard key={client.id} client={client} />)
          ) : (
            <div className="rounded-xl border border-dashed p-8 text-center">
              <KeyRound className="mx-auto size-6 text-muted-foreground" />
              <p className="mt-2 text-sm font-medium">No server credentials yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Create one for each system that should talk to Telejects.
              </p>
            </div>
          )
        ) : clients.error ? (
          <p role="alert" className="text-sm text-destructive">
            {clients.error.message}
          </p>
        ) : (
          <>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </>
        )}
      </div>

      <HowToConnect />

      {revoked.length > 0 && (
        <details className="mt-8">
          <summary className="cursor-pointer text-sm font-medium text-muted-foreground">
            Revoked ({revoked.length})
          </summary>
          <div className="mt-3 grid gap-3">
            {revoked.map((client) => (
              <ClientCard key={client.id} client={client} />
            ))}
          </div>
        </details>
      )}

      {creating && <CreateClientDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function ClientCard({ client }: { client: ApiClient }) {
  const revoke = useRevokeApiClient();
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-medium">{client.name}</h2>
            {!client.active && <Badge variant="secondary">Revoked</Badge>}
          </div>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
            {client.client_id}
          </p>
        </div>
        {client.active && (
          <ConfirmDialog
            title={`Revoke ${client.name}?`}
            description="Its tokens stop working straight away, and it can't ask for new ones. This can't be undone."
            confirmLabel="Revoke"
            destructive
            onConfirm={() => revoke.mutate(client.id)}
          >
            <Button variant="outline" size="sm" disabled={revoke.isPending}>
              Revoke
            </Button>
          </ConfirmDialog>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {client.permissions.map((code) => (
          <Badge key={code} variant="outline" className="font-mono text-[11px]">
            {code}
          </Badge>
        ))}
      </div>
      <dl className="mt-3 grid gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-3">
        <div className="flex gap-1">
          <dt>Created by</dt>
          <dd className="truncate text-foreground">{client.created_by || "Someone removed"}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Created</dt>
          <dd className="text-foreground tabular-nums">{date(client.created_at)}</dd>
        </div>
        <div className="flex gap-1">
          <dt>{client.active ? "Last used" : "Revoked"}</dt>
          <dd className="text-foreground tabular-nums">
            {date(client.active ? client.last_used_at : client.revoked_at)}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function HowToConnect() {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  return (
    <section className="mt-8 rounded-xl border bg-card p-4 text-sm [&_code]:break-all">
      <h2 className="font-medium">How a system connects</h2>
      <ol className="mt-2 grid list-decimal gap-2 pl-5 text-muted-foreground">
        <li>
          It asks for a token:{" "}
          <code className="text-foreground">POST {origin}/api/oauth/token/</code> with{" "}
          <code className="text-foreground">grant_type=client_credentials</code>, its client ID and
          secret. A token lasts an hour.
        </li>
        <li>
          It sends the token as <code className="text-foreground">Authorization: Bearer …</code>{" "}
          with each request.
        </li>
        <li>
          Systems moving from Rapid keep their requests and responses:{" "}
          <code className="text-foreground">/api/single-site-feasibility/</code>,{" "}
          <code className="text-foreground">/api/single-site-feasibility-quote/</code>,{" "}
          <code className="text-foreground">/api/connect-product/</code> and{" "}
          <code className="text-foreground">/api/product/</code>.
        </li>
      </ol>
      <a
        href={API_DOCS_URL}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-flex items-center gap-1 font-medium text-primary underline-offset-4 hover:underline"
      >
        Read the API documentation <ExternalLink className="size-3.5" />
      </a>
    </section>
  );
}
