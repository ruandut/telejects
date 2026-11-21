/** Add or change one price, as Rapid's price book dialog did (staff only). */
import { Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
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

import { useBookConnectProducts, useDeletePrice, useSavePrice } from "../api";
import { PROVIDER, type BookOptions, type PriceDefinition } from "../types";
import { ON_REQUEST } from "./money";

/** A cost field with Rapid's "on request only" box: -1 is stored, the box is shown. */
function CostField({
  id,
  label,
  value,
  onChange,
  required,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const onRequest = Number(value) === ON_REQUEST;
  return (
    <Field label={label} htmlFor={id}>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        max={50000}
        step="0.01"
        required={required && !onRequest}
        disabled={onRequest}
        value={onRequest ? "" : value}
        placeholder={onRequest ? "On request" : "0.00"}
        onChange={(e) => onChange(e.target.value)}
        className="tabular-nums"
      />
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <Checkbox
          checked={onRequest}
          onCheckedChange={(checked) => onChange(checked === true ? String(ON_REQUEST) : "")}
        />
        On request only
      </label>
    </Field>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="grid gap-4">
      <legend className="mb-1 text-sm font-medium">{title}</legend>
      {children}
    </fieldset>
  );
}

export function PriceDialog({
  price,
  options,
  onClose,
}: {
  /** The price to change, or null to add one. */
  price: PriceDefinition | null;
  options: BookOptions;
  onClose: () => void;
}) {
  const save = useSavePrice(price?.id ?? null);
  const remove = useDeletePrice();
  const connectProducts = useBookConnectProducts();
  const [name, setName] = useState(price?.name ?? "");
  const [provider, setProvider] = useState(price?.provider ?? PROVIDER.vodacom);
  const [medium, setMedium] = useState(price?.medium ?? "Fibre");
  const [sublayer, setSublayer] = useState(price?.sublayer ?? null);
  const [accessMedium, setAccessMedium] = useState(price?.access_medium?.id ?? null);
  const [product, setProduct] = useState(price?.product?.id ?? null);
  const [download, setDownload] = useState(String(price?.max_bandwidth ?? ""));
  const [upload, setUpload] = useState(String(price?.max_upload_bandwidth ?? ""));
  const [duration, setDuration] = useState(String(price?.duration ?? 12));
  const [monthly, setMonthly] = useState(price?.monthly_recurring_cost ?? "");
  const [onceOff, setOnceOff] = useState(price?.none_recurring_cost ?? "0.00");
  const [data, setData] = useState(price?.data_allocation ? String(price.data_allocation) : "");
  const [notes, setNotes] = useState(price?.data_allocation_notes ?? "");
  const [inProducts, setInProducts] = useState<number[]>(
    price?.connect_products.map((c) => c.id) ?? [],
  );
  const vodacom = provider === PROVIDER.vodacom;
  const products = options.products.filter((p) => p.provider === provider);

  const changeProvider = (next: number) => {
    setProvider(next);
    if (next !== PROVIDER.vodacom) setAccessMedium(null);
    if (!options.products.some((p) => p.id === product && p.provider === next)) setProduct(null);
  };

  const submit = () =>
    save.mutate(
      {
        name: name.trim(),
        provider,
        medium,
        sublayer,
        access_medium: vodacom ? accessMedium : null,
        product,
        max_bandwidth: Number(download),
        max_upload_bandwidth: Number(upload),
        duration: Number(duration),
        monthly_recurring_cost: monthly,
        none_recurring_cost: onceOff || "0",
        data_allocation: data ? Number(data) : null,
        data_allocation_notes: notes,
        connect_products: inProducts,
      },
      { onSuccess: onClose },
    );

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{price ? price.name : "Add a price"}</DialogTitle>
          <DialogDescription>
            {vodacom
              ? "Vodacom prices an access medium; the product is optional."
              : "This provider prices a product."}{" "}
            Quotes list it where a site is feasible at this download speed.
          </DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-6"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Section title="What it is">
            <Field label="Name" htmlFor="price-name" hint="As quotes and the PDF show it.">
              <Input
                id="price-name"
                required
                minLength={2}
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Sky Connect Fibre"
                autoFocus={!price}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Provider" htmlFor="price-provider">
                <NativeSelect
                  id="price-provider"
                  value={provider}
                  onChange={(e) => changeProvider(Number(e.target.value))}
                >
                  {options.providers.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Medium" htmlFor="price-medium">
                <NativeSelect
                  id="price-medium"
                  value={medium}
                  onChange={(e) => setMedium(e.target.value)}
                >
                  {options.mediums.map((m) => (
                    <option key={m}>{m}</option>
                  ))}
                </NativeSelect>
              </Field>
              <Field
                label="Access medium"
                htmlFor="price-access-medium"
                hint={vodacom ? undefined : "Vodacom only."}
              >
                <NativeSelect
                  id="price-access-medium"
                  disabled={!vodacom}
                  value={accessMedium ?? ""}
                  onChange={(e) => setAccessMedium(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">None</option>
                  {options.access_media.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} ({m.identifier})
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Product" htmlFor="price-product">
                <NativeSelect
                  id="price-product"
                  value={product ?? ""}
                  onChange={(e) => setProduct(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">None</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field
                label="Network"
                htmlFor="price-sublayer"
                hint="Whose network it runs over: the PDF's section and logo."
                className="sm:col-span-2"
              >
                <NativeSelect
                  id="price-sublayer"
                  value={sublayer ?? ""}
                  onChange={(e) => setSublayer(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">None</option>
                  {options.sublayers.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            </div>
          </Section>

          <Section title="Speed and term">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Download (Mbps)" htmlFor="price-down">
                <Input
                  id="price-down"
                  type="number"
                  required
                  min={1}
                  max={10000}
                  value={download}
                  onChange={(e) => setDownload(e.target.value)}
                  className="tabular-nums"
                />
              </Field>
              <Field label="Upload (Mbps)" htmlFor="price-up">
                <Input
                  id="price-up"
                  type="number"
                  required
                  min={1}
                  max={10000}
                  value={upload}
                  onChange={(e) => setUpload(e.target.value)}
                  className="tabular-nums"
                />
              </Field>
              <Field label="Term (months)" htmlFor="price-term">
                <Input
                  id="price-term"
                  type="number"
                  required
                  min={1}
                  max={60}
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  className="tabular-nums"
                />
              </Field>
              <Field label="Data (GB)" htmlFor="price-data" hint="Empty when there's no cap.">
                <Input
                  id="price-data"
                  type="number"
                  min={0}
                  value={data}
                  onChange={(e) => setData(e.target.value)}
                  className="tabular-nums"
                />
              </Field>
              <Field label="Data notes" htmlFor="price-notes" className="sm:col-span-2">
                <Input
                  id="price-notes"
                  maxLength={255}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Uncapped"
                />
              </Field>
            </div>
          </Section>

          <Section title="Cost, excluding VAT">
            <div className="grid gap-4 sm:grid-cols-2">
              <CostField
                id="price-mrc"
                label="Monthly (R)"
                value={monthly}
                onChange={setMonthly}
                required
              />
              <CostField
                id="price-nrc"
                label="Once-off (R)"
                value={onceOff}
                onChange={setOnceOff}
              />
            </div>
          </Section>

          <Section title="Quoted in">
            {connectProducts.data?.length ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {connectProducts.data.map((c) => (
                  <label key={c.id} className="flex min-w-0 items-center gap-2 text-sm">
                    <Checkbox
                      checked={inProducts.includes(c.id)}
                      onCheckedChange={(checked) =>
                        setInProducts((ids) =>
                          checked === true ? [...ids, c.id] : ids.filter((id) => id !== c.id),
                        )
                      }
                    />
                    <span className="truncate">{c.name}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No connect products yet. Add one under Manage products first.
              </p>
            )}
            {!inProducts.length && (
              <p className="text-xs text-muted-foreground">
                In no connect product, it is never quoted.
              </p>
            )}
          </Section>

          <FormError error={save.error} />
          <DialogFooter className="gap-2 sm:justify-between">
            {price ? (
              <ConfirmDialog
                title={`Delete ${price.name}?`}
                description="It goes from the price book and every connect product it is in. Quotes stop listing it at once."
                destructive
                confirmLabel="Delete price"
                onConfirm={() => remove.mutate(price, { onSuccess: onClose })}
              >
                <Button type="button" variant="ghost" className="text-destructive">
                  <Trash2 /> Delete
                </Button>
              </ConfirmDialog>
            ) : (
              <span />
            )}
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" disabled={save.isPending}>
                {price ? "Save" : "Add price"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
