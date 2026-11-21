import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { useEditRunProducts, useRunProducts } from "../api";
import type { Run, RunProduct } from "../types";
import { ProductPicker } from "./product-picker";

/**
 * Changes a finished run's products. Saving runs it again, so the dialog says so: every site is
 * checked against the new picks and the new results replace the ones it has.
 */
export function EditProductsDialog({ run, onClose }: { run: Run; onClose: () => void }) {
  const available = useRunProducts();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit products</DialogTitle>
          <DialogDescription>
            Saving runs this feasibility again: all {run.site_count.toLocaleString("en-ZA")} sites
            are checked against the products you pick, and the new results replace the ones it has
            now.
          </DialogDescription>
        </DialogHeader>
        {available.data ? (
          <Picker run={run} products={available.data} onClose={onClose} />
        ) : available.error ? (
          <p role="alert" className="text-sm text-destructive">
            {available.error.message}
          </p>
        ) : (
          <Skeleton className="h-40 w-full" />
        )}
      </DialogContent>
    </Dialog>
  );
}

function Picker({
  run,
  products,
  onClose,
}: {
  run: Run;
  products: RunProduct[];
  onClose: () => void;
}) {
  const save = useEditRunProducts(run.id);
  const offered = new Set(products.map((p) => p.id));
  const [value, setValue] = useState(() =>
    run.products.map((p) => p.id).filter((id) => offered.has(id)),
  );
  const gone = run.products.filter((p) => !offered.has(p.id));
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.length) save.mutate(value, { onSuccess: onClose });
      }}
    >
      {gone.length > 0 && (
        <p className="text-sm text-muted-foreground">
          No longer offered, so left out: {gone.map((p) => p.name).join(", ")}.
        </p>
      )}
      {products.length ? (
        <ProductPicker products={products} value={value} onChange={setValue} />
      ) : (
        <p className="text-sm text-muted-foreground">No products are offered right now.</p>
      )}
      <DialogFooter className="items-center gap-2 sm:justify-between">
        <p className="order-last text-sm text-muted-foreground sm:order-none">
          {value.length === 1 ? "1 product" : `${value.length} products`} picked
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!value.length || save.isPending}>
            <RefreshCw /> Save and run again
          </Button>
        </div>
      </DialogFooter>
    </form>
  );
}
