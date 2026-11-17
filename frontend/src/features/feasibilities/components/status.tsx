import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import type { ResultStatus, RunStatus } from "../types";

const RESULT_STYLE: Record<ResultStatus, string> = {
  available: "border-transparent bg-primary text-primary-foreground",
  near_net: "border-brand-accent/60 text-brand-accent",
  coverage_only: "border-primary/40 text-primary",
  not_available: "border-transparent bg-muted text-muted-foreground",
};

export function ResultBadge({ status, label }: { status: ResultStatus; label: string }) {
  return (
    <Badge variant="outline" className={cn("max-w-full", RESULT_STYLE[status])}>
      <span className="truncate">{label}</span>
    </Badge>
  );
}

export function StateBadge({ state }: { state: "pending" | "error" | "cancelled" }) {
  if (state === "pending")
    return (
      <Badge variant="outline" className="text-muted-foreground">
        <Loader2 className="size-3 animate-spin" /> Pending
      </Badge>
    );
  if (state === "error") return <Badge variant="destructive">Error</Badge>;
  return (
    <Badge variant="outline" className="text-muted-foreground">
      Cancelled
    </Badge>
  );
}

const RUN_LABEL: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge variant={status === "completed" ? "secondary" : "outline"}>
      {(status === "running" || status === "queued") && <Loader2 className="size-3 animate-spin" />}
      {RUN_LABEL[status]}
    </Badge>
  );
}

export function Progress({ value, total }: { value: number; total: number }) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 min-w-16 flex-1 overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width]"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
        {value.toLocaleString("en-ZA")} / {total.toLocaleString("en-ZA")}
      </span>
    </div>
  );
}
