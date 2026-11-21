/** Rapid's price book table: every price, one line each. A table on wider screens, cards at
 * phone width, so the page never scrolls sideways. */
import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { PROVIDER, type BookOptions, type PriceDefinition } from "../types";
import { cost, speed } from "./money";

/** What Rapid's price book flagged on a row, said as what it means for quotes. */
function problems(price: PriceDefinition): string[] {
  const found = [];
  if (!price.connect_products.length) found.push("In no connect product, so never quoted.");
  if (price.provider === PROVIDER.vodacom && !price.access_medium)
    found.push("Vodacom without an access medium: never matched at a site.");
  if (!price.product) found.push("No product: quotes don't check for it on their own.");
  if (price.sublayer === null) found.push("No network: the PDF lists it without one.");
  return found;
}

function Problems({ price }: { price: PriceDefinition }) {
  const found = problems(price);
  if (!found.length) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label={found.join(" ")}
          className="inline-flex shrink-0 rounded-sm text-brand-accent outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <TriangleAlert className="size-4" />
        </span>
      </TooltipTrigger>
      <TooltipContent className="flex-col items-start gap-0.5">
        {found.map((line) => (
          <span key={line}>{line}</span>
        ))}
      </TooltipContent>
    </Tooltip>
  );
}

function providerLabel(options: BookOptions | undefined, provider: number): string {
  return options?.providers.find((p) => p.value === provider)?.label.replace("_", " ") ?? "";
}

function Name({
  price,
  canEdit,
  onOpen,
}: {
  price: PriceDefinition;
  canEdit: boolean;
  onOpen: (price: PriceDefinition) => void;
}) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {canEdit ? (
        <button
          type="button"
          onClick={() => onOpen(price)}
          className="min-w-0 truncate rounded-sm text-left font-medium outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {price.name}
        </button>
      ) : (
        <span className="min-w-0 truncate font-medium">{price.name}</span>
      )}
      {canEdit && <Problems price={price} />}
    </span>
  );
}

function Clipped({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("block truncate", className)}>{children}</span>;
}

function connectNames(price: PriceDefinition): string {
  return price.connect_products.map((c) => c.name).join(", ") || "—";
}

export function PriceTable({
  prices,
  options,
  canEdit,
  onOpen,
}: {
  prices: PriceDefinition[];
  options: BookOptions | undefined;
  canEdit: boolean;
  onOpen: (price: PriceDefinition) => void;
}) {
  if (!prices.length) {
    return (
      <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
        No prices match.
      </p>
    );
  }
  return (
    <>
      <div className="hidden min-w-0 overflow-hidden rounded-xl border bg-card md:block">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead className="w-56 pl-4">Name</TableHead>
              <TableHead className="w-28">Provider</TableHead>
              <TableHead className="w-24">Medium</TableHead>
              <TableHead className="w-40">Access medium / product</TableHead>
              <TableHead className="w-44">Connect products</TableHead>
              <TableHead className="w-28 text-right">Speed</TableHead>
              <TableHead className="w-28 text-right">Monthly</TableHead>
              <TableHead className="w-28 text-right">Once-off</TableHead>
              <TableHead className="w-20 text-right">Term</TableHead>
              <TableHead className="w-36 pr-4">Data</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {prices.map((price) => (
              <TableRow key={price.id}>
                <TableCell className="pl-4">
                  <Name price={price} canEdit={canEdit} onOpen={onOpen} />
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{providerLabel(options, price.provider)}</Badge>
                </TableCell>
                <TableCell>
                  <Clipped>{price.medium ?? "—"}</Clipped>
                </TableCell>
                <TableCell title={[price.access_medium?.name, price.product?.name].join(" / ")}>
                  <Clipped>{price.access_medium?.name ?? price.product?.name ?? "—"}</Clipped>
                  {price.access_medium && price.product && (
                    <Clipped className="text-xs text-muted-foreground">
                      {price.product.name}
                    </Clipped>
                  )}
                </TableCell>
                <TableCell title={connectNames(price)}>
                  <Clipped className="text-muted-foreground">{connectNames(price)}</Clipped>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {speed(price.max_bandwidth, price.max_upload_bandwidth)}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {cost(price.monthly_recurring_cost)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {cost(price.none_recurring_cost)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{price.duration} mo</TableCell>
                <TableCell className="pr-4" title={price.data_allocation_notes ?? ""}>
                  <Clipped className="tabular-nums">
                    {price.data_allocation ? `${price.data_allocation} GB` : ""}
                    {price.data_allocation && price.data_allocation_notes ? " · " : ""}
                    {price.data_allocation_notes || (price.data_allocation ? "" : "—")}
                  </Clipped>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="grid gap-2 md:hidden">
        {prices.map((price) => (
          <li key={price.id} className="grid min-w-0 gap-2 rounded-xl border bg-card p-3">
            <div className="flex min-w-0 items-start justify-between gap-2">
              <Name price={price} canEdit={canEdit} onOpen={onOpen} />
              <Badge variant="secondary" className="shrink-0">
                {providerLabel(options, price.provider)}
              </Badge>
            </div>
            <div className="truncate text-sm text-muted-foreground">
              {[price.medium, price.access_medium?.name ?? price.product?.name]
                .filter(Boolean)
                .join(" · ")}
            </div>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <div className="grid min-w-0">
                <dt className="text-xs text-muted-foreground">Monthly</dt>
                <dd className="truncate font-medium tabular-nums">
                  {cost(price.monthly_recurring_cost)}
                </dd>
              </div>
              <div className="grid min-w-0">
                <dt className="text-xs text-muted-foreground">Speed</dt>
                <dd className="truncate tabular-nums">
                  {speed(price.max_bandwidth, price.max_upload_bandwidth)}
                </dd>
              </div>
              <div className="grid min-w-0">
                <dt className="text-xs text-muted-foreground">Term</dt>
                <dd className="tabular-nums">{price.duration} mo</dd>
              </div>
            </dl>
            <div className="truncate text-xs text-muted-foreground">{connectNames(price)}</div>
          </li>
        ))}
      </ul>
    </>
  );
}
