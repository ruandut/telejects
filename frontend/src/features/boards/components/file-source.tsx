/** Choosing the spreadsheet a board is made from. */
import { FileUp } from "lucide-react";
import { useState } from "react";

import { ACCEPTED, MAX_ROWS, readRows } from "../file";

export type Picked = { name: string; rows: string[][] };

export function FileSource({
  picked,
  onPick,
}: {
  picked: Picked | null;
  onPick: (file: Picked | null) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  return (
    <div className="grid gap-2">
      <label className="flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground hover:bg-muted/50">
        <FileUp className="size-5" />
        {picked ? (
          <span className="text-foreground">
            <span className="font-medium">{picked.name}</span> ·{" "}
            <span className="tabular-nums">{picked.rows.length.toLocaleString("en-ZA")}</span> rows
          </span>
        ) : reading ? (
          "Reading…"
        ) : (
          "Choose a .xlsx or .csv file"
        )}
        <span className="text-xs">
          A monday.com board export (Board menu → Export → Excel) keeps its groups, statuses, people
          and dates. Any list with a header row works too.
        </span>
        <input
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setError(null);
            setReading(true);
            try {
              const rows = await readRows(file);
              if (rows.length > MAX_ROWS) throw new Error(`Import at most 5,000 items at a time.`);
              onPick({ name: file.name, rows });
            } catch (err) {
              onPick(null);
              setError(err instanceof Error ? err.message : "That file couldn't be read.");
            } finally {
              setReading(false);
            }
          }}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** The board's name a file suggests: monday.com's export starts with it; else the file name. */
export function suggestedName(picked: Picked): string {
  const first = picked.rows[0]?.filter(Boolean) ?? [];
  if (first.length === 1 && picked.rows.some((r) => r[0]?.toLowerCase() === "name"))
    return first[0];
  return picked.name.replace(/\.(csv|xlsx)$/i, "");
}
