import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { NoAccess } from "@/components/no-access";
import { SettingsSection } from "@/components/settings-section";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useLog } from "@/features/logs/api";
import { BodyView, HeadersView } from "@/features/logs/components/body-view";
import { OutcomeBadge } from "@/features/logs/components/outcome";
import type { LogDetail } from "@/features/logs/types";
import { usePermission } from "@/features/realms/permissions";
import { ApiError } from "@/network/errors";

export const Route = createFileRoute("/_app/logs/$logId")({
  component: LogPage,
});

const when = new Intl.DateTimeFormat("en-ZA", { dateStyle: "medium", timeStyle: "medium" });

function LogPage() {
  const me = useMe();
  const canView = usePermission("integrations.logs");
  const id = Number(Route.useParams().logId);
  if (me.data && !canView) return <NoAccess section="Logs" />;
  return <LogView id={id} />;
}

function LogView({ id }: { id: number }) {
  const entry = useLog(id);
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 p-4 md:p-8">
      <Link
        to="/logs"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Logs
      </Link>
      {entry.data ? (
        <Loaded entry={entry.data} />
      ) : entry.error ? (
        <p role="alert" className="rounded-xl border bg-card p-6 text-sm">
          {entry.error instanceof ApiError && entry.error.status === 404
            ? "This request is no longer kept: Telejects keeps only the latest requests for your company."
            : entry.error.message}
        </p>
      ) : (
        <Skeleton className="h-60 w-full" />
      )}
    </div>
  );
}

function Loaded({ entry }: { entry: LogDetail }) {
  return (
    <>
      <div className="grid gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <OutcomeBadge outcome={entry.outcome} status={entry.status_code} />
          <h1 className="text-xl font-semibold tracking-tight">
            {entry.connection_name || "Removed connection"} · {entry.operation_label}
          </h1>
        </div>
        <p className="font-mono text-xs break-all text-muted-foreground">
          {entry.method} {entry.url}
        </p>
        <p className="text-sm text-muted-foreground">
          {when.format(new Date(entry.created_at))}
          {entry.duration_ms !== null && ` · ${entry.duration_ms.toLocaleString("en-ZA")} ms`}
          {entry.attempt > 1 && ` · attempt ${entry.attempt}`}
          {entry.credentials === "platform" && " · Telejects account"}
          {entry.definition_version !== null &&
            ` · ${entry.connector_key} definition v${entry.definition_version}`}
        </p>
        {entry.error && <p className="text-sm text-destructive">{entry.error}</p>}
        <p className="flex flex-wrap gap-3 text-sm">
          {entry.run_id !== null && (
            <Link
              to="/feasibilities/$runId"
              params={{ runId: String(entry.run_id) }}
              className="text-primary underline-offset-4 hover:underline"
            >
              Open the run
            </Link>
          )}
          {entry.connection_id !== null && (
            <Link
              to="/integrations/$connectionId"
              params={{ connectionId: String(entry.connection_id) }}
              className="text-primary underline-offset-4 hover:underline"
            >
              Open the connection
            </Link>
          )}
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <SettingsSection title="Request" description="What Telejects sent. Secrets are redacted.">
          <div className="grid gap-3">
            <HeadersView headers={entry.request_headers} />
            <BodyView body={entry.request_body} empty="No body." />
          </div>
        </SettingsSection>
        <SettingsSection
          title="Response"
          description={
            entry.status_code !== null ? `HTTP ${entry.status_code}` : "No answer came back."
          }
        >
          <div className="grid gap-3">
            <HeadersView headers={entry.response_headers} />
            <BodyView body={entry.response_body} empty="No body." />
          </div>
        </SettingsSection>
      </div>
    </>
  );
}
