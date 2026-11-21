/** Bring sites in from a CSV or Excel file (an export from monday.com works): map the file's
 * columns to the board's, then every row is checked like an edit. */
import { FileUp } from "lucide-react";
import { useState } from "react";

import { Field, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { readSheet } from "@/features/feasibilities/sheet";

import { useItemActions } from "../api";
import { useBoardCtx } from "../board-context";
import type { ImportResult } from "../types";
import { COMPUTED } from "../values";

type Sheet = { headers: string[]; rows: string[][] };

async function read(file: File): Promise<Sheet> {
  const sheet = await readSheet(file);
  return { headers: sheet.columns, rows: sheet.rows };
}

const norm = (s: string) =>
  s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");

export function ImportDialog({ onClose }: { onClose: () => void }) {
  const { board } = useBoardCtx();
  const actions = useItemActions(board.id);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [map, setMap] = useState<Record<number, string>>({});
  const [lat, setLat] = useState<number | null>(null);
  const [lng, setLng] = useState<number | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const targets = board.columns.filter((c) => !COMPUTED.has(c.type) && c.type !== "connect");
  const location = board.columns.find((c) => c.type === "location");

  const load = async (file: File) => {
    try {
      const next = await read(file);
      setSheet(next);
      const guess: Record<number, string> = {};
      next.headers.forEach((h, i) => {
        const n = norm(h);
        if (
          ["name", "site", "sitename", "item"].includes(n) &&
          !Object.values(guess).includes("name")
        )
          guess[i] = "name";
        const match = targets.find((c) => norm(c.title) === n);
        if (match && !guess[i]) guess[i] = match.key;
        if (["lat", "latitude"].includes(n)) setLat(i);
        if (["lng", "lon", "long", "longitude"].includes(n)) setLng(i);
      });
      setMap(guess);
    } catch {
      setError("That file couldn't be read. Use a .csv or .xlsx file.");
    }
  };

  const run = () => {
    if (!sheet) return;
    const nameAt = Number(Object.entries(map).find(([, key]) => key === "name")?.[0] ?? -1);
    const rows = sheet.rows.map((row) => {
      const values: Record<string, unknown> = {};
      for (const [i, key] of Object.entries(map))
        if (key && key !== "name" && row[Number(i)] !== "") values[key] = row[Number(i)];
      if (location && lat !== null && lng !== null && row[lat] && row[lng])
        values[location.key] = {
          lat: row[lat],
          lng: row[lng],
          address: values[location.key] ?? "",
        };
      return { name: nameAt >= 0 ? row[nameAt] : "", values };
    });
    actions.importRows.mutate(rows, { onSuccess: setResult });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import items</DialogTitle>
          <DialogDescription>
            From a CSV or Excel file with a header row. Each row becomes an item in the board's
            first group.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="grid gap-2 text-sm">
            <p>
              <strong className="tabular-nums">{result.created}</strong> imported
              {result.failed > 0 && (
                <>
                  , <strong className="text-destructive tabular-nums">{result.failed}</strong>{" "}
                  skipped
                </>
              )}
              .
            </p>
            {result.errors.length > 0 && (
              <ul className="max-h-60 overflow-y-auto rounded-md border p-2 text-xs">
                {result.errors.map((e) => (
                  <li key={e.row}>
                    Row {e.row + 1}:{" "}
                    {JSON.stringify(e.errors)
                      .replace(/[{}"[\]]/g, " ")
                      .trim()}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : !sheet ? (
          <label className="flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-sm text-muted-foreground hover:bg-muted/50">
            <FileUp className="size-6" />
            Choose a .csv or .xlsx file
            <input
              type="file"
              accept=".csv,.xlsx"
              className="sr-only"
              onChange={(e) => e.target.files?.[0] && void load(e.target.files[0])}
            />
            {error && <span className="text-destructive">{error}</span>}
          </label>
        ) : (
          <div className="grid gap-3">
            <p className="text-sm text-muted-foreground">
              {sheet.rows.length} rows. Match the file's columns to the board's:
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {sheet.headers.map((header, i) => (
                <Field key={i} label={header || `Column ${i + 1}`}>
                  <NativeSelect
                    value={map[i] ?? ""}
                    onChange={(e) => setMap({ ...map, [i]: e.target.value })}
                  >
                    <option value="">Skip</option>
                    <option value="name">Item name</option>
                    {targets.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.title}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              ))}
            </div>
            {location && (
              <div className="grid gap-2 sm:grid-cols-2">
                <Field label={`Latitude for ${location.title}`}>
                  <NativeSelect
                    value={lat ?? ""}
                    onChange={(e) => setLat(e.target.value === "" ? null : Number(e.target.value))}
                  >
                    <option value="">None</option>
                    {sheet.headers.map((h, i) => (
                      <option key={i} value={i}>
                        {h}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
                <Field label={`Longitude for ${location.title}`}>
                  <NativeSelect
                    value={lng ?? ""}
                    onChange={(e) => setLng(e.target.value === "" ? null : Number(e.target.value))}
                  >
                    <option value="">None</option>
                    {sheet.headers.map((h, i) => (
                      <option key={i} value={i}>
                        {h}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {result ? "Done" : "Cancel"}
          </Button>
          {sheet && !result && (
            <Button
              onClick={run}
              disabled={actions.importRows.isPending || !Object.values(map).includes("name")}
            >
              {actions.importRows.isPending ? "Importing…" : `Import ${sheet.rows.length} rows`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
