/** A new board in a project: blank, from a template, or with one item per site of a
 * feasibility run (its answers become the Feasibility columns). */
import { FileSpreadsheet, FileUp, LayoutTemplate, MapPinned } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useRuns } from "@/features/feasibilities/api";
import { usePermission } from "@/features/realms/permissions";
import { cn } from "@/lib/utils";

import { useBoardFromFile, useCreateBoard } from "../api";
import type { Board } from "../types";
import { FileSource, suggestedName, type Picked } from "./file-source";

type Source = "blank" | "site_rollout" | "run" | "file";

const SOURCES: { key: Source; title: string; hint: string; icon: typeof LayoutTemplate }[] = [
  { key: "blank", title: "Blank", hint: "A status, an owner and a date.", icon: FileSpreadsheet },
  {
    key: "site_rollout",
    title: "Site rollout",
    hint: "The rollout columns, with no items yet.",
    icon: LayoutTemplate,
  },
  {
    key: "run",
    title: "From a feasibility run",
    hint: "One item per site, with what the providers said.",
    icon: MapPinned,
  },
  {
    key: "file",
    title: "From a file",
    hint: "A monday.com export, or any CSV or Excel list.",
    icon: FileUp,
  },
];

function RunPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string, name: string) => void;
}) {
  const runs = useRuns();
  const list = runs.data ?? [];
  return (
    <Field
      label="Feasibility run"
      hint="The site list and the answers as they are now. Later changes to the run don't change the board."
    >
      <NativeSelect
        value={value}
        onChange={(e) => {
          const run = list.find((r) => String(r.id) === e.target.value);
          onChange(e.target.value, run?.name ?? "");
        }}
      >
        <option value="">{runs.isLoading ? "Loading runs…" : "Choose a run"}</option>
        {list.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name} · {r.site_count.toLocaleString("en-ZA")} sites
            {r.status === "completed" ? "" : ` · ${r.status}`}
          </option>
        ))}
      </NativeSelect>
      {!runs.isLoading && !list.length && (
        <p className="text-xs text-muted-foreground">No feasibility runs yet.</p>
      )}
    </Field>
  );
}

export function NewBoardDialog({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: number;
  onClose: () => void;
  onCreated: (board: Board) => void;
}) {
  const create = useCreateBoard(projectId);
  const fromFile = useBoardFromFile(projectId);
  const [picked, setPicked] = useState<Picked | null>(null);
  const canUseRuns = usePermission("feasibilities.view");
  const [source, setSource] = useState<Source>("blank");
  const [name, setName] = useState("");
  const [run, setRun] = useState("");
  const shown = SOURCES.filter((s) => s.key !== "run" || canUseRuns);
  const ready = source === "run" ? !!run : source === "file" ? !!picked : true;
  const pending = create.isPending || fromFile.isPending;

  const submit = () => {
    if (source === "file" && picked) {
      fromFile.mutate(
        { name: name.trim(), rows: picked.rows },
        {
          onSuccess: (board) => {
            const { created, failed } = board.import;
            if (failed) toast.warning(`${created} items imported, ${failed} rows skipped`);
            else toast.success(`${created} items imported`);
            onCreated(board);
          },
        },
      );
      return;
    }
    create.mutate(
      source === "run"
        ? { name: name.trim(), template: "site_rollout", feasibility_run: Number(run) }
        : { name: name.trim(), template: source },
      { onSuccess: onCreated },
    );
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) submit();
          }}
        >
          <DialogHeader>
            <DialogTitle>New board</DialogTitle>
            <DialogDescription>
              Another board in this project, such as orders or a second phase.
            </DialogDescription>
          </DialogHeader>
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">Start with</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {shown.map(({ key, title, hint, icon: Icon }) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={source === key}
                  onClick={() => setSource(key)}
                  className={cn(
                    "grid gap-1 rounded-lg border p-3 text-left hover:bg-muted",
                    source === key && "border-primary bg-accent",
                  )}
                >
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="text-sm font-medium">{title}</span>
                  <span className="text-xs text-muted-foreground">{hint}</span>
                </button>
              ))}
            </div>
          </fieldset>
          {source === "run" && (
            <RunPicker
              value={run}
              onChange={(id, runName) => {
                setRun(id);
                if (!name.trim()) setName(runName);
              }}
            />
          )}
          {source === "file" && (
            <FileSource
              picked={picked}
              onPick={(file) => {
                setPicked(file);
                if (file && !name.trim()) setName(suggestedName(file));
              }}
            />
          )}
          <Field label="Name" htmlFor="board-name">
            <Input
              id="board-name"
              value={name}
              maxLength={120}
              placeholder={source === "run" ? "The run's name" : "Orders"}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <FormError error={create.error ?? fromFile.error} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!ready || pending || (!["run", "file"].includes(source) && !name.trim())}
            >
              {pending ? (source === "file" ? "Importing…" : "Creating…") : "Create board"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
