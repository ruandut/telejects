/**
 * Reading an uploaded spreadsheet in the browser (CSV or XLSX), mapping its columns and finding
 * the rows that can't be checked. The server checks every row again with the same rules.
 */
import Papa from "papaparse";

import type { RowInput } from "./types";

export type Sheet = { columns: string[]; rows: string[][] };
export type Mapping = { name: string; latitude: string; longitude: string };
export type BadRow = { line: number; problems: string[] };

const MAX_COLUMNS = 50;

const text = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value as string | number | boolean).trim();
};

function toSheet(data: unknown[][]): Sheet {
  const [header = [], ...body] = data;
  const seen = new Map<string, number>();
  // Blank or repeated headings get a name of their own, so every column can be told apart.
  const columns = header.slice(0, MAX_COLUMNS).map((cell, i) => {
    const base = text(cell) || `Column ${i + 1}`;
    const count = seen.get(base) ?? 0;
    seen.set(base, count + 1);
    return count ? `${base} (${count + 1})` : base;
  });
  const rows = body.map((row) => columns.map((_, i) => text(row[i])));
  return { columns, rows };
}

export async function readSheet(file: File): Promise<Sheet> {
  if (/\.xlsx$/i.test(file.name)) {
    const { readSheet: readXlsx } = await import("read-excel-file/browser");
    return toSheet(await readXlsx(file));
  }
  const parsed = Papa.parse<string[]>(await file.text(), { skipEmptyLines: "greedy" });
  if (parsed.errors.length && !parsed.data.length) throw new Error(parsed.errors[0].message);
  return toSheet(parsed.data);
}

/** A first guess at which columns hold the name and coordinates. */
export function guessMapping(columns: string[]): Mapping {
  const find = (pattern: RegExp) => columns.find((c) => pattern.test(c.toLowerCase())) ?? "";
  return {
    name: find(/name|site/),
    latitude: find(/^lat|latitude/),
    longitude: find(/^lon|^lng|longitude/),
  };
}

function coordinate(value: string, limit: number): boolean {
  if (!/^-?\d+(\.\d+)?$/.test(value.trim())) return false;
  return Math.abs(Number(value)) <= limit;
}

/** Same rules and words as the server (apps/feasibilities/services.py, row_problems). */
export function rowProblems(name: string, latitude: string, longitude: string): string[] {
  const problems: string[] = [];
  if (!name) problems.push("No name.");
  else if (name.length > 100) problems.push("The name is longer than 100 characters.");
  if (!coordinate(latitude, 90)) problems.push("The latitude isn't a number from -90 to 90.");
  if (!coordinate(longitude, 180)) problems.push("The longitude isn't a number from -180 to 180.");
  return problems;
}

/** Line numbers count the heading as line 1, as in the spreadsheet. */
export function buildRows(sheet: Sheet, mapping: Mapping): { good: RowInput[]; bad: BadRow[] } {
  const index = (column: string) => sheet.columns.indexOf(column);
  const [n, lat, lon] = [index(mapping.name), index(mapping.latitude), index(mapping.longitude)];
  const good: RowInput[] = [];
  const bad: BadRow[] = [];
  sheet.rows.forEach((cells, i) => {
    const line = i + 2;
    const name = cells[n] ?? "";
    const latitude = cells[lat] ?? "";
    const longitude = cells[lon] ?? "";
    const problems = rowProblems(name, latitude, longitude);
    if (problems.length) {
      bad.push({ line, problems });
      return;
    }
    good.push({
      line_number: line,
      name,
      latitude,
      longitude,
      row: Object.fromEntries(sheet.columns.map((c, j) => [c, cells[j] ?? ""])),
    });
  });
  return { good, bad };
}
