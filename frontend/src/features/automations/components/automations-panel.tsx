/** A board's automations: each as a sentence, switched on or off, with its recent runs. */
import { Bot, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type { Board } from "@/features/boards/types";
import type { Person } from "@/features/projects/types";
import { cn } from "@/lib/utils";

import { useAutomations, useDeleteAutomation, useRuns, useSaveAutomation } from "../api";
import { describe } from "../describe";
import type { Automation } from "../types";
import { AutomationBuilder } from "./automation-builder";

const RUN_TONE: Record<string, string> = {
  done: "text-label-green",
  failed: "text-destructive",
  skipped: "text-label-amber",
  scheduled: "text-label-blue",
  cancelled: "text-muted-foreground",
};

function Runs({ automation }: { automation: Automation }) {
  const runs = useRuns(automation.id);
  if (runs.isLoading) return <Skeleton className="h-10" />;
  if (!runs.data?.length)
    return <p className="text-xs text-muted-foreground">It hasn't run yet.</p>;
  return (
    <ul className="grid gap-1 text-xs">
      {runs.data.slice(0, 8).map((run) => (
        <li key={run.id} className="flex flex-wrap gap-x-2">
          <span className={cn("font-medium capitalize", RUN_TONE[run.status])}>{run.status}</span>
          <span className="truncate">{run.item_name}</span>
          {run.message && <span className="text-muted-foreground">· {run.message}</span>}
          <time className="ml-auto text-muted-foreground tabular-nums">
            {new Date(
              run.status === "scheduled" && run.due_at ? run.due_at : run.created_at,
            ).toLocaleString("en-ZA", { dateStyle: "short", timeStyle: "short" })}
          </time>
        </li>
      ))}
    </ul>
  );
}

function Row({
  board,
  automation,
  canManage,
  onEdit,
}: {
  board: Board;
  automation: Automation;
  canManage: boolean;
  onEdit: () => void;
}) {
  const save = useSaveAutomation(board.id);
  const remove = useDeleteAutomation(board.id);
  const [open, setOpen] = useState(false);
  return (
    <li className="grid gap-2 rounded-lg border bg-card p-3">
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={automation.enabled}
          aria-label={automation.enabled ? "Switch off" : "Switch on"}
          disabled={!canManage}
          onClick={() => save.mutate({ id: automation.id, enabled: !automation.enabled })}
          className={cn(
            "mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors disabled:opacity-60",
            automation.enabled ? "bg-label-green" : "bg-muted-foreground/40",
          )}
        >
          <span
            className={cn(
              "size-4 rounded-full bg-white transition-transform",
              automation.enabled && "translate-x-4",
            )}
          />
        </button>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{automation.name}</p>
          <p className="text-sm text-muted-foreground">{describe(board, automation)}.</p>
          <button
            type="button"
            className="mt-1 text-xs text-primary hover:underline"
            onClick={() => setOpen((v) => !v)}
          >
            {automation.run_count} run{automation.run_count === 1 ? "" : "s"} ·{" "}
            {open ? "hide history" : "history"}
          </button>
        </div>
        {canManage && (
          <div className="flex shrink-0">
            <Button variant="ghost" size="icon" aria-label="Edit" onClick={onEdit}>
              <Pencil />
            </Button>
            <ConfirmDialog
              title={`Delete ${automation.name}?`}
              description="Waiting actions are dropped too."
              confirmLabel="Delete"
              destructive
              onConfirm={() => remove.mutate(automation.id)}
            >
              <Button variant="ghost" size="icon" aria-label="Delete">
                <Trash2 />
              </Button>
            </ConfirmDialog>
          </div>
        )}
      </div>
      {open && <Runs automation={automation} />}
    </li>
  );
}

export function AutomationsPanel({
  board,
  people,
  open,
  onOpenChange,
}: {
  board: Board;
  people: Person[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const automations = useAutomations(board.id);
  const canManage = board.my_level === "manage";
  const [editing, setEditing] = useState<Automation | "new" | null>(null);
  return (
    <Sheet open={open} onOpenChange={(next) => (setEditing(null), onOpenChange(next))}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Bot className="size-5" /> Automations
            <Badge variant="secondary">
              {automations.data?.filter((a) => a.enabled).length ?? 0} on
            </Badge>
          </SheetTitle>
          <SheetDescription>
            When something happens on {board.name}, do something for you. Dates and schedules are
            checked every minute.
          </SheetDescription>
        </SheetHeader>
        <div className="grid gap-3 px-4 pb-6">
          {editing ? (
            <AutomationBuilder
              board={board}
              people={people}
              automation={editing === "new" ? null : editing}
              onDone={() => setEditing(null)}
            />
          ) : (
            <>
              {canManage && (
                <Button className="justify-self-start" onClick={() => setEditing("new")}>
                  <Plus /> New automation
                </Button>
              )}
              {automations.isLoading && <Skeleton className="h-24" />}
              {automations.data?.length === 0 && (
                <p className="text-sm text-muted-foreground">No automations on this board yet.</p>
              )}
              <ul className="grid gap-2">
                {automations.data?.map((a) => (
                  <Row
                    key={a.id}
                    board={board}
                    automation={a}
                    canManage={canManage}
                    onEdit={() => setEditing(a)}
                  />
                ))}
              </ul>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
