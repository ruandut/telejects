/**
 * Reading a spreadsheet for a new board: every row as text, exactly as laid out, so the server
 * can recognise a monday.com export (board name, group rows, header rows, subitems) as well as
 * a plain list (apps/boards/file_import.py).
 */
import Papa from "papaparse";

const text = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value as string | number | boolean).trim();
};

export const ACCEPTED = ".csv,.xlsx";

export async function readRows(file: File): Promise<string[][]> {
  if (/\.xlsx$/i.test(file.name)) {
    const { readSheet } = await import("read-excel-file/browser");
    const rows = (await readSheet(file)) as unknown[][];
    return rows.map((row) => row.map(text));
  }
  if (!/\.(csv|txt)$/i.test(file.name)) throw new Error("Choose a .csv or .xlsx file.");
  const parsed = Papa.parse<string[]>(await file.text(), { skipEmptyLines: false });
  if (parsed.errors.length && !parsed.data.length) throw new Error(parsed.errors[0].message);
  return parsed.data.map((row) => row.map(text));
}

/** Sends at most this many rows; the server takes 5,000 items. */
export const MAX_ROWS = 6000;
