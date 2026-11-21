/** Create a project (with its first board from a template), or change one. */
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
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

import { useBoardFromFile, useTemplates } from "@/features/boards/api";
import { FileSource, suggestedName, type Picked } from "@/features/boards/components/file-source";
import { LABEL_COLOURS, labelColour } from "@/lib/colours";
import { cn } from "@/lib/utils";

import { useCreateProject, useUpdateProject } from "../api";
import { STATUS_LABELS, type Project, type ProjectStatus } from "../types";

export function ProjectDialog({
  project,
  onClose,
  onCreated,
}: {
  project: Project | null;
  onClose: () => void;
  onCreated?: (p: Project) => void;
}) {
  const create = useCreateProject();
  const update = useUpdateProject(project?.id ?? 0);
  const templates = useTemplates();
  const [name, setName] = useState(project?.name ?? "");
  const [client, setClient] = useState(project?.client ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [status, setStatus] = useState<ProjectStatus>(project?.status ?? "active");
  const [colour, setColour] = useState(project?.colour ?? "blue");
  const [start, setStart] = useState(project?.start_date ?? "");
  const [end, setEnd] = useState(project?.end_date ?? "");
  const [template, setTemplate] = useState("site_rollout");
  const [picked, setPicked] = useState<Picked | null>(null);
  const fromFile = useBoardFromFile(0);
  const importing = template === "file";
  const mutation = project ? update : fromFile.error ? fromFile : create;

  const save = () => {
    const body = {
      name,
      client,
      description,
      status,
      colour,
      start_date: start || null,
      end_date: end || null,
    };
    if (project) update.mutate(body, { onSuccess: onClose });
    else if (importing && picked)
      // The project starts empty, then its board comes from the file.
      create.mutate(
        { ...body, template: "none" },
        {
          onSuccess: (p) =>
            fromFile.mutate(
              { project: p.id, name: suggestedName(picked), rows: picked.rows },
              {
                onSuccess: (board) => {
                  const { created, failed } = board.import;
                  if (failed) toast.warning(`${created} items imported, ${failed} rows skipped`);
                  else toast.success(`${created} items imported`);
                  onCreated?.(p);
                  onClose();
                },
                onError: (error) => {
                  toast.error(
                    `The project was made, but the file wasn't imported: ${error.message}`,
                  );
                  onCreated?.(p);
                  onClose();
                },
              },
            ),
        },
      );
    else create.mutate({ ...body, template }, { onSuccess: (p) => (onCreated?.(p), onClose()) });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{project ? "Project settings" : "New project"}</DialogTitle>
          <DialogDescription>
            {project
              ? "Name, client, dates and status."
              : "A project for a client, with its first board."}
          </DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="p-name">
              <Input
                id="p-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Acme fibre rollout"
                autoFocus
              />
            </Field>
            <Field label="Client" htmlFor="p-client">
              <Input
                id="p-client"
                value={client}
                onChange={(e) => setClient(e.target.value)}
                placeholder="Acme Retail"
              />
            </Field>
          </div>
          {!project && (
            <fieldset className="grid gap-2">
              <legend className="mb-2 text-sm font-medium">Start with</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {templates.data?.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setTemplate(t.key)}
                    aria-pressed={template === t.key}
                    className={cn(
                      "rounded-lg border p-3 text-left hover:bg-muted",
                      template === t.key && "border-primary bg-accent",
                    )}
                  >
                    <span className="block font-medium">{t.name}</span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {t.description}
                    </span>
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setTemplate("file")}
                  aria-pressed={importing}
                  className={cn(
                    "rounded-lg border p-3 text-left hover:bg-muted",
                    importing && "border-primary bg-accent",
                  )}
                >
                  <span className="block font-medium">From a file</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Import a monday.com board export, or any CSV or Excel list.
                  </span>
                </button>
              </div>
              {importing && (
                <FileSource
                  picked={picked}
                  onPick={(file) => {
                    setPicked(file);
                    if (file && !name.trim()) setName(suggestedName(file));
                  }}
                />
              )}
            </fieldset>
          )}
          <Field label="Description" htmlFor="p-desc">
            <Textarea
              id="p-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Status">
              <NativeSelect
                value={status}
                onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              >
                {Object.entries(STATUS_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Starts">
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="Ends">
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Colour</legend>
            <div className="flex flex-wrap gap-2">
              {LABEL_COLOURS.map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-label={c}
                  aria-pressed={colour === c}
                  onClick={() => setColour(c)}
                  className={cn(
                    "size-7 rounded-full ring-offset-2 ring-offset-background",
                    colour === c && "ring-2 ring-ring",
                  )}
                  style={{ background: labelColour(c) }}
                />
              ))}
            </div>
          </fieldset>
          <FormError error={mutation.error} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                create.isPending || fromFile.isPending || !name.trim() || (importing && !picked)
              }
            >
              {project ? "Save" : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
