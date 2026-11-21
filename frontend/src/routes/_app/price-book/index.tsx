import { createFileRoute } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, Download, Pencil, Plus } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { NoAccess } from "@/components/no-access";
import { NativeSelect } from "@/components/form";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { PAGE_SIZE, useBookOptions, useDownloadBook, usePrices } from "@/features/pricebook/api";
import { ConnectProductsDialog } from "@/features/pricebook/components/connect-products-dialog";
import { PriceDialog } from "@/features/pricebook/components/price-dialog";
import { PriceTable } from "@/features/pricebook/components/price-table";
import type { PriceDefinition, PricePage } from "@/features/pricebook/types";
import { usePermission } from "@/features/realms/permissions";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/price-book/")({
  component: PriceBookPage,
});

function PriceBookPage() {
  const me = useMe();
  const canQuote = usePermission("feasibilities.quote");
  if (me.data && !canQuote && !me.data.is_staff) return <NoAccess section="the price book" />;
  return <PriceBook />;
}

function PriceBook() {
  const options = useBookOptions();
  const download = useDownloadBook();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState<number | null>(null);
  const [medium, setMedium] = useState("");
  const typed = useDeferredValue(search.trim());
  const prices = usePrices({ page, search: typed, provider, medium });
  /** The price open in its dialog: one of the list, "new", or none. */
  const [open, setOpen] = useState<PriceDefinition | "new" | null>(null);
  const [managing, setManaging] = useState(false);
  const canEdit = options.data?.can_edit ?? false;

  if (options.isError || prices.isError) {
    return (
      <Shell>
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          {(options.error ?? prices.error)?.message}
        </p>
      </Shell>
    );
  }

  const filter = (change: () => void) => {
    change();
    setPage(1);
  };

  return (
    <Shell
      description={
        canEdit
          ? "Telejects' prices, which quotes list where a site is feasible. Changes apply to every company offered this book at once."
          : "The prices your company's quotes are made from. Prices exclude VAT and aren't final."
      }
      actions={
        <>
          <Button
            variant="outline"
            disabled={download.isPending}
            onClick={() => download.mutate("csv")}
          >
            <Download /> CSV
          </Button>
          <Button
            variant="outline"
            disabled={download.isPending}
            onClick={() => download.mutate("pdf")}
          >
            <Download /> PDF
          </Button>
          {canEdit && (
            <>
              <Button variant="outline" onClick={() => setManaging(true)}>
                <Pencil /> Manage products
              </Button>
              <Button onClick={() => setOpen("new")}>
                <Plus /> Add price
              </Button>
            </>
          )}
        </>
      }
    >
      <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_12rem]">
        <SearchInput
          label="Search prices"
          placeholder="Search by name, product or access medium"
          value={search}
          onChange={(value) => filter(() => setSearch(value))}
        />
        <NativeSelect
          aria-label="Filter by medium"
          value={medium}
          onChange={(e) => filter(() => setMedium(e.target.value))}
        >
          <option value="">Every medium</option>
          {options.data?.mediums.map((m) => (
            <option key={m}>{m}</option>
          ))}
        </NativeSelect>
      </div>
      <div role="group" aria-label="Filter by provider" className="flex flex-wrap gap-1.5">
        {[{ value: null, label: "All providers" }, ...(options.data?.providers ?? [])].map((p) => (
          <Button
            key={p.label}
            size="sm"
            variant={provider === p.value ? "default" : "outline"}
            aria-pressed={provider === p.value}
            className={cn("rounded-full")}
            onClick={() => filter(() => setProvider(p.value))}
          >
            {p.label.replace("_", " ")}
          </Button>
        ))}
      </div>

      {prices.data ? (
        <div className={cn("grid gap-3", prices.isPlaceholderData && "opacity-60")}>
          <PriceTable
            prices={prices.data.results}
            options={options.data}
            canEdit={canEdit}
            onOpen={setOpen}
          />
          {prices.data.count > 0 && <Pager data={prices.data} page={page} onPage={setPage} />}
        </div>
      ) : (
        <Skeleton className="h-64 w-full rounded-xl" />
      )}

      {open && options.data && (
        <PriceDialog
          key={open === "new" ? "new" : open.id}
          price={open === "new" ? null : open}
          options={options.data}
          onClose={() => setOpen(null)}
        />
      )}
      {managing && <ConnectProductsDialog onClose={() => setManaging(false)} />}
    </Shell>
  );
}

function Shell({
  description,
  actions,
  children,
}: {
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mx-auto grid w-full max-w-7xl gap-4 p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">Price book</h1>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

/** "101–200 of 312", and previous and next, 100 a page as in Rapid. */
function Pager({
  data,
  page,
  onPage,
}: {
  data: PricePage;
  page: number;
  onPage: (page: number) => void;
}) {
  const first = (page - 1) * PAGE_SIZE + 1;
  const last = first + data.results.length - 1;
  return (
    <div className="flex items-center justify-end gap-2 text-sm">
      <span className="text-muted-foreground tabular-nums" aria-live="polite">
        {first}–{last} of {data.count}
      </span>
      <Button
        variant="outline"
        size="icon"
        aria-label="Previous page"
        disabled={!data.previous}
        onClick={() => onPage(page - 1)}
      >
        <ChevronLeft />
      </Button>
      <Button
        variant="outline"
        size="icon"
        aria-label="Next page"
        disabled={!data.next}
        onClick={() => onPage(page + 1)}
      >
        <ChevronRight />
      </Button>
    </div>
  );
}
