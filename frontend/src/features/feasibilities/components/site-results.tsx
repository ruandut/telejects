import type { ReactNode } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import type { RunProduct, Site } from "../types";
import { ResultBadge, StateBadge } from "./status";

function bandwidth(ranges: [number | null, number | null][]): string {
  return ranges
    .map(([low, high]) => (low === high || high === null ? `${low}` : `${low ?? 0}–${high}`))
    .join(", ");
}

/** What one site has for one product: its results (per variant), or why there are none. */
function Cell({ site, product }: { site: Site; product: RunProduct }) {
  const results = site.results.filter((r) => r.product === product.id);
  if (results.length) {
    return (
      <div className="flex flex-wrap gap-1">
        {results.map((result, i) => (
          <span
            key={i}
            className="inline-flex max-w-full items-center gap-1"
            title={[
              result.variant_name,
              result.product_type_label,
              bandwidth(result.bandwidths) && `${bandwidth(result.bandwidths)} Mbps`,
              result.note,
            ]
              .filter(Boolean)
              .join(" · ")}
          >
            {result.variant_name && (
              <span className="truncate text-xs text-muted-foreground">{result.variant_name}</span>
            )}
            <ResultBadge status={result.status} label={result.status_label} />
          </span>
        ))}
      </div>
    );
  }
  if (site.errors.some((e) => e.connection === product.connection))
    return <StateBadge state="error" />;
  if (site.state === "pending") return <StateBadge state="pending" />;
  if (site.state === "cancelled") return <StateBadge state="cancelled" />;
  return null;
}

function Errors({ site }: { site: Site }): ReactNode {
  if (!site.errors.length) return null;
  return (
    <ul className="mt-1 grid gap-0.5 text-xs text-destructive">
      {site.errors.map((e) => (
        <li key={e.connection}>
          {e.connection_name}: {e.message}
        </li>
      ))}
    </ul>
  );
}

/** A table on wider screens; cards at phone width, so nothing scrolls sideways. */
export function SiteResults({ sites, products }: { sites: Site[]; products: RunProduct[] }) {
  if (!sites.length) {
    return (
      <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
        No sites match.
      </p>
    );
  }
  return (
    <>
      <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-14 pl-4">Line</TableHead>
              <TableHead>Site</TableHead>
              {products.map((product) => (
                <TableHead key={product.id} className="min-w-36 whitespace-normal">
                  <span className="block text-xs font-normal text-muted-foreground">
                    {product.connection_name}
                  </span>
                  {product.name}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sites.map((site) => (
              <TableRow key={site.id} className="align-top">
                <TableCell className="pl-4 text-muted-foreground tabular-nums">
                  {site.line_number}
                </TableCell>
                <TableCell className="max-w-64 whitespace-normal">
                  <div className="font-medium">{site.name}</div>
                  <div className="text-xs text-muted-foreground tabular-nums">
                    {site.latitude}, {site.longitude}
                  </div>
                  <Errors site={site} />
                </TableCell>
                {products.map((product) => (
                  <TableCell key={product.id} className="whitespace-normal">
                    <Cell site={site} product={product} />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="grid gap-2 md:hidden">
        {sites.map((site) => (
          <li key={site.id} className="rounded-xl border bg-card p-4">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{site.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                Line {site.line_number}
              </span>
            </div>
            <Errors site={site} />
            <dl className="mt-3 grid gap-2 text-sm">
              {products.map((product) => (
                <div key={product.id} className="grid gap-1">
                  <dt className="text-xs text-muted-foreground">
                    {product.connection_name}: {product.name}
                  </dt>
                  <dd>
                    <Cell site={site} product={product} />
                  </dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
