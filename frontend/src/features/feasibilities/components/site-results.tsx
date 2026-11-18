import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePermission } from "@/features/realms/permissions";

import type { RunProduct, Site } from "../types";
import { ResultBadge, StateBadge } from "./status";

function bandwidth(ranges: [number | null, number | null][]): string {
  return ranges
    .map(([low, high]) => (low === high || high === null ? `${low}` : `${low ?? 0}–${high}`))
    .join(", ");
}

/** One result on one line: the variant (cut short if it's long) and its status. Hover or focus
 * it for the whole of it. */
function Result({ result }: { result: Site["results"][number] }) {
  const details = [
    result.variant_name,
    result.product_type_label,
    bandwidth(result.bandwidths) && `${bandwidth(result.bandwidths)} Mbps`,
    result.note,
  ].filter(Boolean);
  const badge = <ResultBadge status={result.status} label={result.status_label} />;
  if (!details.length) return badge;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className="flex max-w-full min-w-0 items-center gap-1.5 rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {result.variant_name && (
            <span className="min-w-0 truncate text-xs text-muted-foreground">
              {result.variant_name}
            </span>
          )}
          <span className="ml-auto flex shrink-0">{badge}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent className="flex-col items-start gap-0.5">
        {details.map((line, i) => (
          <span key={i}>{line}</span>
        ))}
      </TooltipContent>
    </Tooltip>
  );
}

/** What one site has for one product: its results (per variant), or why there are none. */
function Cell({ site, product }: { site: Site; product: RunProduct }) {
  const results = site.results.filter((r) => r.product === product.id);
  if (results.length) {
    return (
      <ul className="grid min-w-0 gap-1">
        {results.map((result, i) => (
          <li key={i} className="flex min-w-0">
            <Result result={result} />
          </li>
        ))}
      </ul>
    );
  }
  if (site.errors.some((e) => e.connection === product.connection))
    return <StateBadge state="error" />;
  if (site.state === "pending") return <StateBadge state="pending" />;
  if (site.state === "cancelled") return <StateBadge state="cancelled" />;
  // Answered, and nothing for this product can be delivered: only feasible results are kept.
  return <ResultBadge status="not_available" label="Not available" />;
}

function Errors({ site }: { site: Site }): ReactNode {
  const seesLogs = usePermission("integrations.logs");
  if (!site.errors.length) return null;
  return (
    <ul className="mt-1 grid gap-0.5 text-xs text-destructive">
      {site.errors.map((e) => (
        <li key={e.connection}>
          {e.connection_name}: {e.message}
          {seesLogs && e.log !== null && (
            <>
              {" "}
              <Link
                to="/logs/$logId"
                params={{ logId: String(e.log) }}
                className="text-primary underline-offset-4 hover:underline"
              >
                See the request
              </Link>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A table on wider screens; cards at phone width, so the page never scrolls sideways. */
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
      {/* Columns keep a steady width and long text is cut short (whole on hover), so rows stay
          one line per result; the table scrolls sideways inside its card when it must. */}
      <div className="hidden min-w-0 overflow-hidden rounded-xl border bg-card md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-14 pl-4">Line</TableHead>
              <TableHead>Site</TableHead>
              {products.map((product) => (
                <TableHead key={product.id} className="h-auto py-2 align-bottom">
                  <div
                    className="max-w-60 min-w-44"
                    title={`${product.connection_name}: ${product.name}`}
                  >
                    <span className="block truncate text-xs font-normal text-muted-foreground">
                      {product.connection_name}
                    </span>
                    <span className="block truncate">{product.name}</span>
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {sites.map((site) => (
              <TableRow key={site.id}>
                <TableCell className="pl-4 align-top text-muted-foreground tabular-nums">
                  {site.line_number}
                </TableCell>
                <TableCell className="align-top">
                  <div className="max-w-56 min-w-40 whitespace-normal">
                    <div className="truncate font-medium" title={site.name}>
                      {site.name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground tabular-nums">
                      {site.latitude}, {site.longitude}
                    </div>
                    <Errors site={site} />
                  </div>
                </TableCell>
                {products.map((product) => (
                  <TableCell key={product.id} className="align-top">
                    <div className="max-w-60 min-w-44">
                      <Cell site={site} product={product} />
                    </div>
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="grid min-w-0 gap-2 md:hidden">
        {sites.map((site) => (
          <li key={site.id} className="min-w-0 rounded-xl border bg-card p-4">
            <div className="flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{site.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                Line {site.line_number}
              </span>
            </div>
            <Errors site={site} />
            <dl className="mt-3 grid gap-2 text-sm">
              {products.map((product) => (
                <div key={product.id} className="grid min-w-0 gap-1">
                  <dt className="truncate text-xs text-muted-foreground">
                    {product.connection_name}: {product.name}
                  </dt>
                  <dd className="min-w-0">
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
