/** Rapid's "Manage products": the connect products a quote is asked for (staff only). */
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Field, FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import { useBookConnectProducts, useDeleteConnectProduct, useSaveConnectProduct } from "../api";
import type { BookConnectProduct } from "../types";

function Editor({ product, onDone }: { product: BookConnectProduct | null; onDone: () => void }) {
  const save = useSaveConnectProduct(product?.id ?? null);
  const [name, setName] = useState(product?.name ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  return (
    <form
      className="grid gap-3 rounded-xl border bg-muted/30 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate({ name: name.trim(), description }, { onSuccess: onDone });
      }}
    >
      <Field label="Name" htmlFor="cp-name" hint="Clients quote for it by its id.">
        <Input
          id="cp-name"
          required
          minLength={2}
          maxLength={255}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Sky Connect Fibre"
          autoFocus
        />
      </Field>
      <Field label="Description" htmlFor="cp-description">
        <Textarea
          id="cp-description"
          rows={2}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <FormError error={save.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {product ? "Save" : "Add"}
        </Button>
      </div>
    </form>
  );
}

export function ConnectProductsDialog({ onClose }: { onClose: () => void }) {
  const products = useBookConnectProducts();
  const remove = useDeleteConnectProduct();
  /** The one being edited: an id, "new", or none. */
  const [editing, setEditing] = useState<number | "new" | null>(null);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Connect products</DialogTitle>
          <DialogDescription>
            What clients quote for. Each one groups prices; add prices to it from a price's own
            dialog.
          </DialogDescription>
        </DialogHeader>
        {editing === "new" ? (
          <Editor product={null} onDone={() => setEditing(null)} />
        ) : (
          <Button
            variant="outline"
            className="justify-self-start"
            onClick={() => setEditing("new")}
          >
            <Plus /> Add a connect product
          </Button>
        )}
        {products.data ? (
          <ul className="grid gap-2">
            {products.data.map((product) =>
              editing === product.id ? (
                <li key={product.id}>
                  <Editor product={product} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li
                  key={product.id}
                  className="flex min-w-0 items-start gap-3 rounded-xl border bg-card p-3"
                >
                  <div className="grid min-w-0 flex-1 gap-0.5">
                    <span className="truncate font-medium">{product.name}</span>
                    {product.description && (
                      <span className="line-clamp-2 text-sm text-muted-foreground">
                        {product.description}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground tabular-nums">
                      id {product.id} · {product.definition_count}{" "}
                      {product.definition_count === 1 ? "price" : "prices"}
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Edit ${product.name}`}
                    onClick={() => setEditing(product.id)}
                  >
                    <Pencil />
                  </Button>
                  <ConfirmDialog
                    title={`Delete ${product.name}?`}
                    description="Clients asking for its id get an error from then on. Its prices stay in the price book."
                    destructive
                    confirmLabel="Delete connect product"
                    onConfirm={() => remove.mutate(product)}
                  >
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${product.name}`}
                      className="text-destructive"
                    >
                      <Trash2 />
                    </Button>
                  </ConfirmDialog>
                </li>
              ),
            )}
          </ul>
        ) : (
          <Skeleton className="h-32" />
        )}
      </DialogContent>
    </Dialog>
  );
}
