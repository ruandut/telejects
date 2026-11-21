/** Adding a column, or changing one's settings: labels, units, formulas, what it connects. */
import { GripVertical, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { useBoard, useBoards, useColumnActions } from "@/features/boards/api";
import { LABEL_COLOURS, labelColour } from "@/lib/colours";

import type { Board, Column, ColumnSettings, ColumnType, Label } from "../types";
import { TYPE_LABELS } from "../values";

const ADDABLE: ColumnType[] = [
  "status",
  "text",
  "long_text",
  "number",
  "date",
  "timeline",
  "people",
  "dropdown",
  "checkbox",
  "rating",
  "location",
  "link",
  "email",
  "phone",
  "formula",
  "connect",
  "mirror",
  "item_id",
  "created",
  "updated",
];

const HINTS: Partial<Record<ColumnType, string>> = {
  status: "Coloured labels; mark the ones that mean done.",
  formula: "Works things out from other columns, like {Monthly fee} * {Term (months)}.",
  connect: "Links items on another board, such as each site's order.",
  mirror: "Shows a column of the items a connect column links to.",
  people: "Anyone who can open this project.",
  location: "An address and coordinates.",
};

function newLabel(i: number): Label {
  return {
    id: `n${Date.now().toString(36)}${i}`,
    label: "",
    colour: LABEL_COLOURS[(i + 1) % LABEL_COLOURS.length],
    done: false,
  };
}

function LabelsEditor({
  labels,
  onChange,
  done,
}: {
  labels: Label[];
  onChange: (labels: Label[]) => void;
  done: boolean;
}) {
  const set = (i: number, patch: Partial<Label>) =>
    onChange(labels.map((l, n) => (n === i ? { ...l, ...patch } : l)));
  return (
    <div className="grid gap-1.5">
      {labels.map((label, i) => (
        <div key={label.id} className="flex items-center gap-2">
          <GripVertical className="size-4 shrink-0 text-muted-foreground/50" aria-hidden />
          <NativeSelect
            aria-label="Colour"
            className="w-9 shrink-0 px-0 text-transparent"
            style={{ background: labelColour(label.colour) }}
            value={label.colour}
            onChange={(e) => set(i, { colour: e.target.value })}
          >
            {LABEL_COLOURS.map((c) => (
              <option key={c} value={c} className="text-foreground">
                {c}
              </option>
            ))}
          </NativeSelect>
          <Input
            value={label.label}
            aria-label="Label"
            onChange={(e) => set(i, { label: e.target.value })}
          />
          {done && (
            <label className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
              <Checkbox checked={label.done} onCheckedChange={(v) => set(i, { done: !!v })} /> Done
            </label>
          )}
          <Button
            variant="ghost"
            size="icon"
            aria-label="Remove label"
            onClick={() => onChange(labels.filter((_, n) => n !== i))}
          >
            <Trash2 />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        className="justify-self-start"
        onClick={() => onChange([...labels, newLabel(labels.length)])}
      >
        <Plus /> Add label
      </Button>
    </div>
  );
}

function ConnectSettings({
  board,
  settings,
  onChange,
}: {
  board: Board;
  settings: ColumnSettings;
  onChange: (s: ColumnSettings) => void;
}) {
  const boards = useBoards(board.project.id);
  return (
    <Field
      label="Board to connect"
      hint="Boards of this project. Others can be linked through automations."
    >
      <NativeSelect
        value={settings.board ?? ""}
        onChange={(e) => onChange({ ...settings, board: Number(e.target.value) || undefined })}
      >
        <option value="">Choose a board</option>
        {boards.data?.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );
}

function MirrorSettings({
  board,
  settings,
  onChange,
}: {
  board: Board;
  settings: ColumnSettings;
  onChange: (s: ColumnSettings) => void;
}) {
  const connects = board.columns.filter((c) => c.type === "connect");
  const via = connects.find((c) => c.key === settings.connect_column);
  const target = useBoard(via?.settings.board ?? 0);
  return (
    <>
      <Field label="Through">
        <NativeSelect
          value={settings.connect_column ?? ""}
          onChange={(e) => onChange({ ...settings, connect_column: e.target.value })}
        >
          <option value="">Choose a connect column</option>
          {connects.map((c) => (
            <option key={c.key} value={c.key}>
              {c.title}
            </option>
          ))}
        </NativeSelect>
      </Field>
      {via && (
        <Field label="Column to show">
          <NativeSelect
            value={settings.target_column ?? ""}
            onChange={(e) => onChange({ ...settings, target_column: e.target.value })}
          >
            <option value="">Choose a column</option>
            <option value="name">Item name</option>
            {target.data?.columns
              .filter((c) => !["formula", "mirror", "connect"].includes(c.type))
              .map((c) => (
                <option key={c.key} value={c.key}>
                  {c.title}
                </option>
              ))}
          </NativeSelect>
        </Field>
      )}
      {!connects.length && (
        <p className="text-sm text-muted-foreground">Add a connect column first.</p>
      )}
    </>
  );
}

export function ColumnDialog({
  board,
  column,
  after,
  onClose,
}: {
  board: Board;
  /** null: a new column. */
  column: Column | null;
  after?: string | null;
  onClose: () => void;
}) {
  const actions = useColumnActions(board.id);
  const [type, setType] = useState<ColumnType>(column?.type ?? "status");
  const [title, setTitle] = useState(column?.title ?? "");
  const [description, setDescription] = useState(column?.description ?? "");
  const [settings, setSettings] = useState<ColumnSettings>(
    column?.settings ?? { labels: [newLabel(0), { ...newLabel(1), done: true }] },
  );
  const mutation = column ? actions.update : actions.create;
  const labelsKey = type === "dropdown" ? "options" : "labels";

  const save = () => {
    const body = { title: title || TYPE_LABELS[type], description, settings };
    const done = () => onClose();
    if (column) actions.update.mutate({ id: column.id, ...body }, { onSuccess: done });
    else actions.create.mutate({ ...body, type, after }, { onSuccess: done });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{column ? `${column.title} settings` : "Add a column"}</DialogTitle>
          <DialogDescription>
            {HINTS[type] ?? `A ${TYPE_LABELS[type].toLowerCase()} column.`}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          {!column && (
            <Field label="Type" htmlFor="col-type">
              <NativeSelect
                id="col-type"
                value={type}
                onChange={(e) => {
                  const next = e.target.value as ColumnType;
                  setType(next);
                  setSettings(
                    next === "status"
                      ? { labels: [newLabel(0), { ...newLabel(1), done: true }] }
                      : next === "dropdown"
                        ? { options: [] }
                        : {},
                  );
                }}
              >
                {ADDABLE.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABELS[t]}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}
          <Field label="Title" htmlFor="col-title">
            <Input
              id="col-title"
              value={title}
              placeholder={TYPE_LABELS[type]}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </Field>
          {(type === "status" || type === "dropdown") && (
            <Field label={type === "status" ? "Labels" : "Options"}>
              <LabelsEditor
                labels={settings[labelsKey] ?? []}
                done={type === "status"}
                onChange={(labels) => setSettings({ ...settings, [labelsKey]: labels })}
              />
            </Field>
          )}
          {type === "number" && (
            <div className="grid grid-cols-3 gap-2">
              <Field label="Unit">
                <Input
                  value={settings.unit ?? ""}
                  placeholder="R, Mbps"
                  onChange={(e) => setSettings({ ...settings, unit: e.target.value })}
                />
              </Field>
              <Field label="Shown">
                <NativeSelect
                  value={settings.unit_position ?? "left"}
                  onChange={(e) =>
                    setSettings({ ...settings, unit_position: e.target.value as "left" | "right" })
                  }
                >
                  <option value="left">Before</option>
                  <option value="right">After</option>
                </NativeSelect>
              </Field>
              <Field label="Decimals">
                <Input
                  type="number"
                  min={0}
                  max={6}
                  value={settings.decimals ?? ""}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      decimals: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                />
              </Field>
            </div>
          )}
          {type === "rating" && (
            <Field label="Out of">
              <Input
                type="number"
                min={1}
                max={10}
                value={settings.max ?? 5}
                onChange={(e) => setSettings({ ...settings, max: Number(e.target.value) })}
              />
            </Field>
          )}
          {type === "formula" && (
            <>
              <Field
                label="Formula"
                hint="Column titles in braces. Functions: IF, SUM, AVG, MIN, MAX, ROUND, ABS, DAYS, ADD_DAYS, TODAY, CONCAT, LEN, UPPER, LOWER, BLANK."
              >
                <Textarea
                  className="font-mono text-xs"
                  rows={3}
                  value={settings.expression ?? ""}
                  placeholder="{Monthly fee} * {Term (months)}"
                  onChange={(e) => setSettings({ ...settings, expression: e.target.value })}
                />
              </Field>
              <div className="flex flex-wrap gap-1">
                {board.columns
                  .filter((c) => c.key !== column?.key)
                  .map((c) => (
                    <button
                      key={c.key}
                      type="button"
                      className="rounded-md border px-1.5 py-0.5 text-xs hover:bg-muted"
                      onClick={() =>
                        setSettings({
                          ...settings,
                          expression: `${settings.expression ?? ""}{${c.title}}`,
                        })
                      }
                    >
                      {c.title}
                    </button>
                  ))}
              </div>
              <Field label="Unit (optional)">
                <Input
                  value={settings.unit ?? ""}
                  placeholder="R"
                  onChange={(e) => setSettings({ ...settings, unit: e.target.value })}
                />
              </Field>
            </>
          )}
          {type === "connect" && (
            <ConnectSettings board={board} settings={settings} onChange={setSettings} />
          )}
          {type === "mirror" && (
            <MirrorSettings board={board} settings={settings} onChange={setSettings} />
          )}
          <Field label="Description (optional)">
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </Field>
          <FormError error={mutation.error} />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} disabled={mutation.isPending}>
            {column ? "Save" : "Add column"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
