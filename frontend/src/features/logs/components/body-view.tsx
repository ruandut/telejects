import { useMemo } from "react";

/** A request or response body: JSON pretty-printed, anything else as it came. */
export function BodyView({ body, empty }: { body: string; empty: string }) {
  const text = useMemo(() => {
    if (!body) return "";
    try {
      return JSON.stringify(JSON.parse(body), null, 2);
    } catch {
      return body;
    }
  }, [body]);
  if (!text) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">
      {text}
    </pre>
  );
}

export function HeadersView({ headers }: { headers: Record<string, string> }) {
  const entries = Object.entries(headers ?? {});
  if (!entries.length) return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-muted-foreground">Headers ({entries.length})</summary>
      <dl className="mt-2 grid gap-1 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
        {entries.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="truncate font-medium">{name}</dt>
            <dd className="break-all text-muted-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
