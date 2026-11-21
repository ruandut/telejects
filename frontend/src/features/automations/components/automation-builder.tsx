/** "When … and only if … then …": building one automation from the recipe parts. */
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useBoard, useBoards } from "@/features/boards/api";
import type { Board, Column } from "@/features/boards/types";
import { str, COMPUTED, FILTER_OPS, labelsOf } from "@/features/boards/values";
import type { Person } from "@/features/projects/types";

import { useSaveAutomation } from "../api";
import { describe } from "../describe";
import type { Action, Automation, AutomationInput, Condition, Trigger } from "../types";

const TRIGGERS: { type: Trigger["type"]; label: string }[] = [
  { type: "status_changed", label: "When a status changes" },
  { type: "column_changed", label: "When a column changes" },
  { type: "item_created", label: "When an item is created" },
  { type: "item_moved", label: "When an item moves to a group" },
  { type: "date_arrives", label: "When a date arrives" },
  { type: "schedule", label: "Every day, week or month" },
];

const ACTIONS: { type: Action["type"]; label: string }[] = [
  { type: "set_value", label: "Set a column" },
  { type: "copy_value", label: "Copy a column to another" },
  { type: "clear_value", label: "Clear a column" },
  { type: "increment", label: "Add to a number" },
  { type: "move_to_group", label: "Move to a group" },
  { type: "notify", label: "Notify people" },
  { type: "create_item", label: "Create an item on a board" },
  { type: "archive_item", label: "Archive the item" },
];

function blankTrigger(type: Trigger["type"], board: Board): Trigger {
  const status = board.columns.find((c) => c.type === "status")?.key ?? "";
  const date = board.columns.find((c) => c.type === "date" || c.type === "timeline")?.key ?? "";
  switch (type) {
    case "item_created":
      return { type };
    case "column_changed":
      return { type, column: null };
    case "status_changed":
      return { type, column: status, to: [] };
    case "item_moved":
      return { type, group: null };
    case "date_arrives":
      return { type, column: date, when: "before", days: 1, time: "08:00" };
    case "schedule":
      return { type, every: "week", weekday: 0, time: "08:00" };
  }
}

function blankAction(type: Action["type"], board: Board): Action {
  const writable = board.columns.find((c) => !COMPUTED.has(c.type))?.key ?? "";
  switch (type) {
    case "set_value":
      return { type, column: writable, value: null };
    case "clear_value":
      return { type, column: writable };
    case "copy_value":
      return { type, from: "name", to: writable };
    case "increment":
      return { type, column: board.columns.find((c) => c.type === "number")?.key ?? "", by: 1 };
    case "move_to_group":
      return { type, group: board.groups[0]?.id ?? 0 };
    case "notify":
      return {
        type,
        people_column: board.columns.find((c) => c.type === "people")?.key ?? null,
        members: [],
        trigger_person: false,
        message: "{name}: ",
      };
    case "create_item":
      return { type, board: board.id, group: null, name: "{name}", copy: [], link_column: null };
    case "archive_item":
      return { type };
  }
}

function ColumnSelect({
  columns,
  value,
  onChange,
  withName,
  label = "Column",
  allowAny,
}: {
  columns: Column[];
  value: string | null;
  onChange: (key: string) => void;
  withName?: boolean;
  label?: string;
  allowAny?: boolean;
}) {
  return (
    <NativeSelect aria-label={label} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
      {allowAny ? (
        <option value="">Any column</option>
      ) : (
        <option value="" disabled>
          Choose a column
        </option>
      )}
      {withName && <option value="name">Item name</option>}
      {columns.map((c) => (
        <option key={c.key} value={c.key}>
          {c.title}
        </option>
      ))}
    </NativeSelect>
  );
}

function SetValue({
  column,
  value,
  onChange,
  people,
}: {
  column: Column | undefined;
  value: unknown;
  onChange: (v: unknown) => void;
  people: Person[];
}) {
  if (!column) return null;
  if (column.type === "status" || column.type === "dropdown")
    return (
      <NativeSelect
        aria-label="Value"
        value={str(value)}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Choose</option>
        {labelsOf(column).map((l) => (
          <option key={l.id} value={l.id}>
            {l.label}
          </option>
        ))}
      </NativeSelect>
    );
  if (column.type === "people")
    return (
      <NativeSelect
        aria-label="Person"
        value={Array.isArray(value) ? String(value[0]) : str(value)}
        onChange={(e) =>
          onChange(
            ["trigger_person", "creator"].includes(e.target.value)
              ? e.target.value
              : [Number(e.target.value)],
          )
        }
      >
        <option value="">Choose</option>
        <option value="trigger_person">The person who made the change</option>
        <option value="creator">The item's creator</option>
        {people.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </NativeSelect>
    );
  if (column.type === "date") {
    const relative = value && typeof value === "object" && "today_plus" in (value as object);
    const days = relative ? (value as { today_plus: number }).today_plus : 0;
    return (
      <div className="flex items-center gap-2">
        <NativeSelect
          aria-label="When"
          className="w-36"
          value={relative ? "relative" : "date"}
          onChange={(e) => onChange(e.target.value === "relative" ? { today_plus: 0 } : "")}
        >
          <option value="relative">Today +</option>
          <option value="date">A date</option>
        </NativeSelect>
        {relative ? (
          <Input
            type="number"
            aria-label="Days from today"
            className="w-24"
            value={days}
            onChange={(e) => onChange({ today_plus: Number(e.target.value) })}
          />
        ) : (
          <Input
            type="date"
            aria-label="Date"
            value={str(value)}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </div>
    );
  }
  if (column.type === "checkbox")
    return (
      <NativeSelect
        aria-label="Value"
        value={value ? "true" : ""}
        onChange={(e) => onChange(e.target.value === "true")}
      >
        <option value="true">Checked</option>
        <option value="">Unchecked</option>
      </NativeSelect>
    );
  return <Input aria-label="Value" value={str(value)} onChange={(e) => onChange(e.target.value)} />;
}

function OtherBoard({
  action,
  onChange,
  source,
}: {
  action: Extract<Action, { type: "create_item" }>;
  onChange: (a: Action) => void;
  source: Board;
}) {
  const project = source.project.id;
  const boards = useBoards(project);
  const target = useBoard(action.board);
  return (
    <div className="grid gap-2">
      <div className="grid gap-2 sm:grid-cols-2">
        <NativeSelect
          aria-label="Board"
          value={action.board}
          onChange={(e) =>
            onChange({ ...action, board: Number(e.target.value), group: null, copy: [] })
          }
        >
          {boards.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Group"
          value={action.group ?? ""}
          onChange={(e) =>
            onChange({ ...action, group: e.target.value ? Number(e.target.value) : null })
          }
        >
          <option value="">Its first group</option>
          {target.data?.groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </NativeSelect>
      </div>
      <Input
        aria-label="New item's name"
        value={action.name}
        onChange={(e) => onChange({ ...action, name: e.target.value })}
        placeholder="{name}"
      />
      {target.data && (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={action.copy.length > 0}
            onCheckedChange={(on) => {
              if (!on || !target.data) return onChange({ ...action, copy: [] });
              const pairs = source.columns
                .map((c) => ({
                  c,
                  t: target.data!.columns.find(
                    (t) => t.title.toLowerCase() === c.title.toLowerCase() && !COMPUTED.has(t.type),
                  ),
                }))
                .filter((p) => p.t)
                .map((p) => ({ from: p.c.key, to: p.t!.key }));
              onChange({ ...action, copy: pairs });
            }}
          />
          Copy the columns both boards have{action.copy.length ? ` (${action.copy.length})` : ""}
        </label>
      )}
      {source.columns.some((c) => c.type === "connect" && c.settings.board === action.board) && (
        <NativeSelect
          aria-label="Link back"
          value={action.link_column ?? ""}
          onChange={(e) => onChange({ ...action, link_column: e.target.value || null })}
        >
          <option value="">Don't link it to this item</option>
          {source.columns
            .filter((c) => c.type === "connect" && c.settings.board === action.board)
            .map((c) => (
              <option key={c.key} value={c.key}>
                Link it through {c.title}
              </option>
            ))}
        </NativeSelect>
      )}
    </div>
  );
}

export function AutomationBuilder({
  board,
  people,
  automation,
  onDone,
}: {
  board: Board;
  people: Person[];
  automation: Automation | null;
  onDone: () => void;
}) {
  const save = useSaveAutomation(board.id);
  const [name, setName] = useState(automation?.name ?? "");
  const [trigger, setTrigger] = useState<Trigger>(
    automation?.trigger ?? blankTrigger("status_changed", board),
  );
  const [conditions, setConditions] = useState<Condition[]>(automation?.conditions ?? []);
  const [actions, setActions] = useState<Action[]>(
    automation?.actions ?? [blankAction("set_value", board)],
  );
  const [delay, setDelay] = useState(automation?.delay ?? null);
  const columns = board.columns;
  const writable = columns.filter((c) => !COMPUTED.has(c.type));
  const draft: AutomationInput = {
    name: name || "Untitled automation",
    trigger,
    conditions,
    actions,
    delay,
  };
  const setAction = (i: number, a: Action) => setActions(actions.map((x, n) => (n === i ? a : x)));
  const statusCol =
    trigger.type === "status_changed" ? columns.find((c) => c.key === trigger.column) : undefined;

  return (
    <div className="grid gap-5">
      <p className="rounded-lg border bg-muted/40 p-3 text-sm">
        {describe(board, {
          ...draft,
          id: 0,
          board: board.id,
          enabled: true,
          created_by_name: null,
          created_at: "",
          updated_at: "",
          run_count: 0,
          last_run_at: null,
        })}
        .
      </p>
      <Field label="Name">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Stamp the go-live date"
        />
      </Field>

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-semibold">When</legend>
        <NativeSelect
          aria-label="Trigger"
          value={trigger.type}
          onChange={(e) => setTrigger(blankTrigger(e.target.value as Trigger["type"], board))}
        >
          {TRIGGERS.map((t) => (
            <option key={t.type} value={t.type}>
              {t.label}
            </option>
          ))}
        </NativeSelect>
        {trigger.type === "column_changed" && (
          <ColumnSelect
            columns={columns}
            value={trigger.column}
            allowAny
            onChange={(column) => setTrigger({ ...trigger, column: column || null })}
          />
        )}
        {trigger.type === "status_changed" && (
          <>
            <ColumnSelect
              columns={columns.filter((c) => c.type === "status")}
              value={trigger.column}
              onChange={(column) => setTrigger({ ...trigger, column, to: [] })}
            />
            {statusCol && (
              <div className="flex flex-wrap gap-2">
                <span className="text-sm text-muted-foreground">to</span>
                {labelsOf(statusCol).map((l) => (
                  <label key={l.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={trigger.to.includes(l.id)}
                      onCheckedChange={(on) =>
                        setTrigger({
                          ...trigger,
                          to: on ? [...trigger.to, l.id] : trigger.to.filter((x) => x !== l.id),
                        })
                      }
                    />
                    {l.label}
                  </label>
                ))}
                <span className="text-xs text-muted-foreground">(none ticked: any label)</span>
              </div>
            )}
          </>
        )}
        {trigger.type === "item_moved" && (
          <NativeSelect
            aria-label="Group"
            value={trigger.group ?? ""}
            onChange={(e) =>
              setTrigger({ ...trigger, group: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">Any group</option>
            {board.groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </NativeSelect>
        )}
        {trigger.type === "date_arrives" && (
          <div className="grid gap-2 sm:grid-cols-[5rem_8rem_1fr_7rem]">
            <Input
              type="number"
              min={0}
              max={365}
              aria-label="Days"
              disabled={trigger.when === "on"}
              value={trigger.days}
              onChange={(e) => setTrigger({ ...trigger, days: Number(e.target.value) })}
            />
            <NativeSelect
              aria-label="Before or after"
              value={trigger.when}
              onChange={(e) => setTrigger({ ...trigger, when: e.target.value as "before" })}
            >
              <option value="before">days before</option>
              <option value="on">on the day of</option>
              <option value="after">days after</option>
            </NativeSelect>
            <ColumnSelect
              columns={columns.filter((c) => c.type === "date" || c.type === "timeline")}
              value={trigger.column}
              onChange={(column) => setTrigger({ ...trigger, column })}
            />
            <Input
              type="time"
              aria-label="At"
              value={trigger.time}
              onChange={(e) => setTrigger({ ...trigger, time: e.target.value })}
            />
          </div>
        )}
        {trigger.type === "schedule" && (
          <div className="grid gap-2 sm:grid-cols-3">
            <NativeSelect
              aria-label="How often"
              value={trigger.every}
              onChange={(e) =>
                setTrigger({ ...trigger, every: e.target.value as "week", weekday: 0, day: 1 })
              }
            >
              <option value="day">Every day</option>
              <option value="weekday">Every weekday</option>
              <option value="week">Every week on</option>
              <option value="month">Every month on day</option>
            </NativeSelect>
            {trigger.every === "week" && (
              <NativeSelect
                aria-label="Day"
                value={trigger.weekday ?? 0}
                onChange={(e) => setTrigger({ ...trigger, weekday: Number(e.target.value) })}
              >
                {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
                  (d, i) => (
                    <option key={d} value={i}>
                      {d}
                    </option>
                  ),
                )}
              </NativeSelect>
            )}
            {trigger.every === "month" && (
              <Input
                type="number"
                min={1}
                max={28}
                aria-label="Day of month"
                value={trigger.day ?? 1}
                onChange={(e) => setTrigger({ ...trigger, day: Number(e.target.value) })}
              />
            )}
            <Input
              type="time"
              aria-label="At"
              value={trigger.time}
              onChange={(e) => setTrigger({ ...trigger, time: e.target.value })}
            />
          </div>
        )}
        {trigger.type === "schedule" && (
          <p className="text-xs text-muted-foreground">
            Runs the actions for every item that meets the conditions.
          </p>
        )}
      </fieldset>

      <fieldset className="grid gap-2">
        <legend className="mb-2 text-sm font-semibold">Only if</legend>
        {conditions.map((c, i) => {
          const column = columns.find((x) => x.key === c.column);
          const op = FILTER_OPS.find((o) => o.op === c.op);
          return (
            <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-1.5">
              <ColumnSelect
                columns={columns}
                value={c.column}
                onChange={(column) =>
                  setConditions(
                    conditions.map((x, n) => (n === i ? { ...x, column, value: "" } : x)),
                  )
                }
              />
              <NativeSelect
                aria-label="Comparison"
                value={c.op}
                onChange={(e) =>
                  setConditions(
                    conditions.map((x, n) => (n === i ? { ...x, op: e.target.value } : x)),
                  )
                }
              >
                {FILTER_OPS.map((o) => (
                  <option key={o.op} value={o.op}>
                    {o.label}
                  </option>
                ))}
              </NativeSelect>
              {op?.needsValue ? (
                column?.type === "status" || column?.type === "dropdown" ? (
                  <NativeSelect
                    aria-label="Value"
                    value={str(c.value)}
                    onChange={(e) =>
                      setConditions(
                        conditions.map((x, n) => (n === i ? { ...x, value: e.target.value } : x)),
                      )
                    }
                  >
                    <option value="">Choose</option>
                    {labelsOf(column).map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.label}
                      </option>
                    ))}
                  </NativeSelect>
                ) : (
                  <Input
                    aria-label="Value"
                    value={str(c.value)}
                    onChange={(e) =>
                      setConditions(
                        conditions.map((x, n) => (n === i ? { ...x, value: e.target.value } : x)),
                      )
                    }
                  />
                )
              ) : (
                <span />
              )}
              <Button
                variant="ghost"
                size="icon"
                aria-label="Remove condition"
                onClick={() => setConditions(conditions.filter((_, n) => n !== i))}
              >
                <Trash2 />
              </Button>
            </div>
          );
        })}
        <Button
          variant="outline"
          size="sm"
          className="justify-self-start"
          onClick={() =>
            setConditions([...conditions, { column: columns[0]?.key ?? "", op: "is", value: "" }])
          }
        >
          <Plus /> Add a condition
        </Button>
      </fieldset>

      <fieldset className="grid gap-3">
        <legend className="mb-2 text-sm font-semibold">Then</legend>
        <label className="flex flex-wrap items-center gap-2 text-sm">
          <Checkbox
            checked={!!delay}
            onCheckedChange={(on) => setDelay(on ? { amount: 1, unit: "days" } : null)}
          />
          Wait first
          {delay && (
            <>
              <Input
                type="number"
                min={1}
                max={365}
                className="w-20"
                aria-label="How long"
                value={delay.amount}
                onChange={(e) => setDelay({ ...delay, amount: Number(e.target.value) })}
              />
              <NativeSelect
                className="w-28"
                aria-label="Unit"
                value={delay.unit}
                onChange={(e) => setDelay({ ...delay, unit: e.target.value as "days" })}
              >
                <option value="minutes">minutes</option>
                <option value="hours">hours</option>
                <option value="days">days</option>
              </NativeSelect>
            </>
          )}
        </label>
        {actions.map((action, i) => (
          <div key={i} className="grid gap-2 rounded-lg border p-3">
            <div className="flex gap-2">
              <NativeSelect
                aria-label="Action"
                value={action.type}
                onChange={(e) => setAction(i, blankAction(e.target.value as Action["type"], board))}
              >
                {ACTIONS.map((a) => (
                  <option key={a.type} value={a.type}>
                    {a.label}
                  </option>
                ))}
              </NativeSelect>
              {actions.length > 1 && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove action"
                  onClick={() => setActions(actions.filter((_, n) => n !== i))}
                >
                  <Trash2 />
                </Button>
              )}
            </div>
            {action.type === "set_value" && (
              <div className="grid gap-2 sm:grid-cols-2">
                <ColumnSelect
                  columns={writable}
                  value={action.column}
                  onChange={(column) => setAction(i, { ...action, column, value: null })}
                />
                <SetValue
                  column={columns.find((c) => c.key === action.column)}
                  value={action.value}
                  people={people}
                  onChange={(value) => setAction(i, { ...action, value })}
                />
              </div>
            )}
            {action.type === "clear_value" && (
              <ColumnSelect
                columns={writable}
                value={action.column}
                onChange={(column) => setAction(i, { ...action, column })}
              />
            )}
            {action.type === "copy_value" && (
              <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                <ColumnSelect
                  columns={columns}
                  withName
                  value={action.from}
                  label="From"
                  onChange={(from) => setAction(i, { ...action, from })}
                />
                <span className="text-center text-sm text-muted-foreground">into</span>
                <ColumnSelect
                  columns={writable}
                  withName
                  value={action.to}
                  label="To"
                  onChange={(to) => setAction(i, { ...action, to })}
                />
              </div>
            )}
            {action.type === "increment" && (
              <div className="grid gap-2 sm:grid-cols-2">
                <ColumnSelect
                  columns={columns.filter((c) => c.type === "number")}
                  value={action.column}
                  onChange={(column) => setAction(i, { ...action, column })}
                />
                <Input
                  type="number"
                  aria-label="By"
                  value={action.by}
                  onChange={(e) => setAction(i, { ...action, by: e.target.value })}
                />
              </div>
            )}
            {action.type === "move_to_group" && (
              <NativeSelect
                aria-label="Group"
                value={action.group}
                onChange={(e) => setAction(i, { ...action, group: Number(e.target.value) })}
              >
                {board.groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </NativeSelect>
            )}
            {action.type === "notify" && (
              <div className="grid gap-2">
                <NativeSelect
                  aria-label="People column"
                  value={action.people_column ?? ""}
                  onChange={(e) =>
                    setAction(i, { ...action, people_column: e.target.value || null })
                  }
                >
                  <option value="">No people column</option>
                  {columns
                    .filter((c) => c.type === "people")
                    .map((c) => (
                      <option key={c.key} value={c.key}>
                        The item's {c.title}
                      </option>
                    ))}
                </NativeSelect>
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {people.map((p) => (
                    <label key={p.id} className="flex items-center gap-1.5 text-sm">
                      <Checkbox
                        checked={action.members.includes(p.id)}
                        onCheckedChange={(on) =>
                          setAction(i, {
                            ...action,
                            members: on
                              ? [...action.members, p.id]
                              : action.members.filter((x) => x !== p.id),
                          })
                        }
                      />
                      {p.name}
                    </label>
                  ))}
                  <label className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={action.trigger_person}
                      onCheckedChange={(on) => setAction(i, { ...action, trigger_person: !!on })}
                    />
                    Whoever made the change
                  </label>
                </div>
                <Input
                  aria-label="Message"
                  value={action.message}
                  placeholder="{name} is now {Status}"
                  onChange={(e) => setAction(i, { ...action, message: e.target.value })}
                />
                <p className="text-xs text-muted-foreground">
                  Use {"{name}"} and {"{Column title}"} in the message.
                </p>
              </div>
            )}
            {action.type === "create_item" && (
              <OtherBoard action={action} source={board} onChange={(a) => setAction(i, a)} />
            )}
          </div>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="justify-self-start"
          onClick={() => setActions([...actions, blankAction("set_value", board)])}
        >
          <Plus /> Add an action
        </Button>
      </fieldset>

      <FormError error={save.error} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button
          disabled={save.isPending}
          onClick={() => save.mutate({ ...draft, id: automation?.id }, { onSuccess: onDone })}
        >
          {automation ? "Save automation" : "Create automation"}
        </Button>
      </div>
    </div>
  );
}
