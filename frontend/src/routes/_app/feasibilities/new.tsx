import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, FileUp } from "lucide-react";
import { useMemo, useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { NoAccess } from "@/components/no-access";
import { SettingsSection } from "@/components/settings-section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useRunProducts, useStartRun } from "@/features/feasibilities/api";
import { ProductPicker } from "@/features/feasibilities/components/product-picker";
import {
  buildRows,
  guessMapping,
  readSheet,
  type Mapping,
  type Sheet,
} from "@/features/feasibilities/sheet";
import { usePermission } from "@/features/realms/permissions";

export const Route = createFileRoute("/_app/feasibilities/new")({
  component: NewRunPage,
});

const MAX_ROWS = 10_000;

function NewRunPage() {
  const me = useMe();
  const canRun = usePermission("feasibilities.run");
  if (me.data && !canRun) return <NoAccess section="new feasibility runs" />;
  return <NewRun />;
}

function NewRun() {
  const [name, setName] = useState("");
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [fileName, setFileName] = useState("");
  const [readError, setReadError] = useState<Error | null>(null);
  const [mapping, setMapping] = useState<Mapping>({ name: "", latitude: "", longitude: "" });
  const [products, setProducts] = useState<number[]>([]);
  const available = useRunProducts();
  const start = useStartRun();
  const navigate = useNavigate();

  const mapped = !!(sheet && mapping.name && mapping.latitude && mapping.longitude);
  const built = useMemo(
    () => (sheet && mapped ? buildRows(sheet, mapping) : null),
    [sheet, mapping, mapped],
  );
  const tooMany = (built?.good.length ?? 0) > MAX_ROWS;
  const ready = !!name.trim() && !!built?.good.length && !tooMany && products.length > 0;

  const choose = async (file: File | undefined) => {
    setReadError(null);
    setSheet(null);
    if (!file) return;
    try {
      const read = await readSheet(file);
      if (!read.rows.length) throw new Error("That file has no rows under its headings.");
      setSheet(read);
      setFileName(file.name);
      setMapping(guessMapping(read.columns));
      if (!name) setName(file.name.replace(/\.(csv|xlsx)$/i, ""));
    } catch (error) {
      setReadError(error instanceof Error ? error : new Error("That file couldn't be read."));
    }
  };

  const submit = () => {
    if (!sheet || !built) return;
    start.mutate(
      {
        name: name.trim(),
        products,
        rows: built.good,
        columns: sheet.columns,
        mapping: { ...mapping },
      },
      {
        onSuccess: (run) =>
          void navigate({ to: "/feasibilities/$runId", params: { runId: String(run.id) } }),
      },
    );
  };

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 p-4 md:p-8">
      <Link
        to="/feasibilities"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Feasibilities
      </Link>
      <h1 className="text-2xl font-semibold tracking-tight">New feasibility run</h1>

      <SettingsSection
        title="1. Sites"
        description="A CSV or Excel (.xlsx) file with a heading row."
      >
        <div className="grid gap-4">
          <Label htmlFor="sites-file" fileName={fileName} />
          <input
            id="sites-file"
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            onChange={(e) => void choose(e.target.files?.[0])}
          />
          <FormError error={readError} />
          {sheet && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                {(["name", "latitude", "longitude"] as const).map((key) => (
                  <Field
                    key={key}
                    label={`${key[0].toUpperCase()}${key.slice(1)} column`}
                    htmlFor={`map-${key}`}
                  >
                    <NativeSelect
                      id={`map-${key}`}
                      value={mapping[key]}
                      onChange={(e) => setMapping((m) => ({ ...m, [key]: e.target.value }))}
                    >
                      <option value="">Choose…</option>
                      {sheet.columns.map((column) => (
                        <option key={column} value={column}>
                          {column}
                        </option>
                      ))}
                    </NativeSelect>
                  </Field>
                ))}
              </div>
              {built && (
                <div className="grid gap-2 text-sm">
                  <p>
                    <span className="font-medium tabular-nums">
                      {built.good.length.toLocaleString("en-ZA")}
                    </span>{" "}
                    sites will be checked
                    {built.bad.length > 0 && (
                      <>
                        ;{" "}
                        <span className="font-medium text-destructive tabular-nums">
                          {built.bad.length.toLocaleString("en-ZA")}
                        </span>{" "}
                        {built.bad.length === 1 ? "row" : "rows"} will be left out:
                      </>
                    )}
                  </p>
                  {tooMany && (
                    <p className="text-destructive">
                      A run can check up to 10,000 sites. Split the file.
                    </p>
                  )}
                  {built.bad.length > 0 && (
                    <ul className="max-h-48 overflow-y-auto rounded-lg border bg-muted/40 p-3 text-xs">
                      {built.bad.slice(0, 200).map((row) => (
                        <li key={row.line}>
                          <span className="font-medium tabular-nums">Line {row.line}:</span>{" "}
                          {row.problems.join(" ")}
                        </li>
                      ))}
                      {built.bad.length > 200 && <li>…and {built.bad.length - 200} more.</li>}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </SettingsSection>

      <SettingsSection
        title="2. Products"
        description="What to check each site for, from your connected providers."
      >
        {available.data ? (
          available.data.length ? (
            <ProductPicker products={available.data} value={products} onChange={setProducts} />
          ) : (
            <p className="text-sm text-muted-foreground">
              No products yet.{" "}
              <Link to="/integrations" className="text-primary underline-offset-4 hover:underline">
                Connect a provider
              </Link>{" "}
              first.
            </p>
          )
        ) : (
          <Skeleton className="h-24 w-full" />
        )}
      </SettingsSection>

      <SettingsSection
        title="3. Start"
        description="Results show line by line as providers answer."
      >
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Field label="Run name" htmlFor="run-name">
            <Input
              id="run-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              required
            />
          </Field>
          <FormError error={start.error} />
          <div className="flex justify-end">
            <Button type="submit" disabled={!ready || start.isPending}>
              {start.isPending ? "Starting…" : "Start run"}
            </Button>
          </div>
        </form>
      </SettingsSection>
    </div>
  );
}

function Label({ htmlFor, fileName }: { htmlFor: string; fileName: string }) {
  return (
    <label
      htmlFor={htmlFor}
      className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed p-6 text-center text-sm outline-none hover:bg-accent/50 focus-within:ring-3 focus-within:ring-ring/50"
    >
      <FileUp className="size-6 text-muted-foreground" />
      <span className="font-medium">{fileName || "Choose a file"}</span>
      <span className="text-xs text-muted-foreground">
        {fileName ? "Choose another to replace it." : "CSV or XLSX, up to 10,000 sites."}
      </span>
    </label>
  );
}
