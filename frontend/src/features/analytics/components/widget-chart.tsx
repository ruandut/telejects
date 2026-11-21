/**
 * Draws a widget's data. Fixed series colours (src/lib/colours.ts, validated for colour-blind
 * separation), a status label's own colour where the data has one, thin marks with rounded data
 * ends, a hover tooltip on every chart, a legend when there are two or more series, one axis.
 */
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { labelColour, seriesColour } from "@/lib/colours";

import type { WidgetData, WidgetKind } from "../types";

const compact = (n: number) =>
  Math.abs(n) >= 1000
    ? n.toLocaleString("en-ZA", { notation: "compact", maximumFractionDigits: 1 })
    : n.toLocaleString("en-ZA", { maximumFractionDigits: 2 });

function shortLabel(label: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(label))
    return new Date(`${label}T00:00:00`).toLocaleDateString("en-ZA", {
      day: "numeric",
      month: "short",
    });
  if (/^\d{4}-\d{2}$/.test(label))
    return new Date(`${label}-01T00:00:00`).toLocaleDateString("en-ZA", {
      month: "short",
      year: "2-digit",
    });
  return label.length > 14 ? `${label.slice(0, 13)}…` : label;
}

export function WidgetChart({
  kind,
  data,
  height = 220,
}: {
  kind: WidgetKind;
  data: WidgetData;
  height?: number;
}) {
  if (kind === "number")
    return (
      <div className="flex flex-col justify-center py-4" style={{ minHeight: height / 2 }}>
        <p className="text-4xl font-semibold tracking-tight tabular-nums">
          {data.total === null ? "–" : compact(data.total)}
        </p>
        <p className="mt-1 text-xs text-muted-foreground tabular-nums">
          across {data.items.toLocaleString("en-ZA")} items
        </p>
      </div>
    );
  if (!data.labels.length)
    return (
      <p
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        Nothing to show yet.
      </p>
    );

  const multi = data.series.length > 1;
  const config: ChartConfig = Object.fromEntries(
    data.series.map((s, i) => [`s${i}`, { label: s.name, color: seriesColour(i, s.colour) }]),
  );
  const rows = data.labels.map((label, i) => ({
    label,
    ...Object.fromEntries(data.series.map((s, n) => [`s${n}`, s.data[i] ?? 0])),
  }));

  if (kind === "table")
    return (
      <div className="max-h-72 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
            <tr>
              <th className="py-1 text-left font-medium" />
              {data.series.map((s) => (
                <th key={s.key} className="py-1 text-right font-medium">
                  {s.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.labels.map((label, i) => (
              <tr key={label} className="border-t">
                <td className="py-1.5 pr-2">{label}</td>
                {data.series.map((s) => (
                  <td key={s.key} className="py-1.5 text-right tabular-nums">
                    {s.data[i] === null ? "–" : compact(s.data[i]!)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );

  if (kind === "pie") {
    const series = data.series[0];
    const slices = data.labels.map((label, i) => ({
      label,
      value: series.data[i] ?? 0,
      fill: data.colours[i] ? labelColour(data.colours[i]) : seriesColour(i),
    }));
    const pieConfig: ChartConfig = Object.fromEntries(
      slices.map((s) => [s.label, { label: s.label, color: s.fill }]),
    );
    const total = slices.reduce((a, s) => a + s.value, 0);
    return (
      <div className="grid min-w-0 gap-3">
        <ChartContainer config={pieConfig} className="mx-auto aspect-auto h-36 w-full">
          <PieChart>
            <ChartTooltip content={<ChartTooltipContent nameKey="label" hideLabel />} />
            <Pie
              data={slices}
              dataKey="value"
              nameKey="label"
              innerRadius="60%"
              strokeWidth={2}
              stroke="var(--card)"
            >
              {slices.map((s) => (
                <Cell key={s.label} fill={s.fill} />
              ))}
            </Pie>
          </PieChart>
        </ChartContainer>
        <ul className="grid min-w-0 gap-1 text-sm">
          {slices.map((s) => (
            <li key={s.label} className="flex min-w-0 items-center gap-2">
              <span className="size-2.5 shrink-0 rounded-sm" style={{ background: s.fill }} />
              <span className="min-w-0 flex-1 truncate">{s.label}</span>
              <span className="shrink-0 tabular-nums">{compact(s.value)}</span>
              <span className="w-9 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                {total ? Math.round((100 * s.value) / total) : 0}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  const axes = (
    <>
      <CartesianGrid vertical={false} strokeOpacity={0.5} />
      <XAxis
        dataKey="label"
        tickLine={false}
        axisLine={false}
        tickMargin={8}
        minTickGap={12}
        tickFormatter={shortLabel}
      />
      <YAxis
        tickLine={false}
        axisLine={false}
        width={44}
        tickFormatter={compact}
        allowDecimals={false}
      />
      <ChartTooltip
        cursor={
          kind === "bar" || kind === "stacked" ? { fill: "var(--muted)", opacity: 0.5 } : true
        }
        content={<ChartTooltipContent indicator={kind === "line" ? "line" : "dot"} />}
      />
      {multi && <ChartLegend content={<ChartLegendContent />} />}
    </>
  );

  if (kind === "line" || kind === "area") {
    const Chart = kind === "line" ? LineChart : AreaChart;
    return (
      <ChartContainer config={config} className="w-full" style={{ height }}>
        <Chart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
          {axes}
          {data.series.map((s, i) =>
            kind === "line" ? (
              <Line
                key={s.key}
                dataKey={`s${i}`}
                type="monotone"
                stroke={`var(--color-s${i})`}
                strokeWidth={2}
                dot={rows.length <= 12 ? { r: 3 } : false}
                activeDot={{ r: 4 }}
              />
            ) : (
              <Area
                key={s.key}
                dataKey={`s${i}`}
                type="monotone"
                stroke={`var(--color-s${i})`}
                fill={`var(--color-s${i})`}
                fillOpacity={0.18}
                strokeWidth={2}
                stackId={multi ? "a" : undefined}
              />
            ),
          )}
        </Chart>
      </ChartContainer>
    );
  }

  const stacked = kind === "stacked" && multi;
  return (
    <ChartContainer config={config} className="w-full" style={{ height }}>
      <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }} barCategoryGap="22%" barGap={2}>
        {axes}
        {data.series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={`s${i}`}
            stackId={stacked ? "a" : undefined}
            fill={`var(--color-s${i})`}
            radius={stacked ? (i === data.series.length - 1 ? [4, 4, 0, 0] : 0) : [4, 4, 0, 0]}
            stroke={stacked ? "var(--card)" : undefined}
            strokeWidth={stacked ? 1 : 0}
            maxBarSize={48}
          >
            {!multi &&
              data.colours.some(Boolean) &&
              rows.map((r, n) => (
                <Cell
                  key={r.label}
                  fill={data.colours[n] ? labelColour(data.colours[n]) : `var(--color-s0)`}
                />
              ))}
          </Bar>
        ))}
      </BarChart>
    </ChartContainer>
  );
}
