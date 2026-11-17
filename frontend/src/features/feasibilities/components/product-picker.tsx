import { useMemo, useState } from "react";

import { NativeSelect } from "@/components/form";
import { Label } from "@/components/ui/label";

import type { RunProduct } from "../types";

const TYPE_LABEL: Record<string, string> = {
  fibre: "Fibre",
  fixed_wireless: "Fixed wireless",
  lte: "LTE",
  "5g": "5G",
  microwave: "Microwave",
  satellite: "Satellite",
  other: "Other",
};

/** Products grouped by provider connection, filterable by type. */
export function ProductPicker({
  products,
  value,
  onChange,
}: {
  products: RunProduct[];
  value: number[];
  onChange: (ids: number[]) => void;
}) {
  const [type, setType] = useState("");
  const types = useMemo(() => [...new Set(products.map((p) => p.product_type))].sort(), [products]);
  const groups = useMemo(() => {
    const byConnection = new Map<string, RunProduct[]>();
    for (const product of products) {
      if (type && product.product_type !== type) continue;
      const list = byConnection.get(product.connection_name) ?? [];
      list.push(product);
      byConnection.set(product.connection_name, list);
    }
    return [...byConnection.entries()];
  }, [products, type]);
  const chosen = new Set(value);
  const toggle = (id: number) =>
    onChange(chosen.has(id) ? value.filter((v) => v !== id) : [...value, id]);

  return (
    <div className="grid gap-3">
      <NativeSelect
        aria-label="Filter by type"
        value={type}
        onChange={(e) => setType(e.target.value)}
        className="sm:max-w-56"
      >
        <option value="">All types</option>
        {types.map((t) => (
          <option key={t} value={t}>
            {TYPE_LABEL[t] ?? t}
          </option>
        ))}
      </NativeSelect>
      {groups.map(([connection, list]) => (
        <fieldset key={connection} className="rounded-xl border p-3">
          <legend className="px-1 text-sm font-medium">{connection}</legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {list.map((product) => (
              <Label
                key={product.id}
                className="flex min-w-0 cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 font-normal hover:bg-accent/50"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={chosen.has(product.id)}
                  onChange={() => toggle(product.id)}
                />
                <span className="min-w-0 flex-1 truncate">{product.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {TYPE_LABEL[product.product_type] ?? product.product_type}
                </span>
              </Label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
