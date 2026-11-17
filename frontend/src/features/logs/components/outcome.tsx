import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  ok: "OK",
  auth: "Credentials refused",
  rate_limited: "Rate limited",
  timeout: "Timed out",
  provider_down: "Provider down",
  bad_request: "Rejected",
  bad_response: "Unreadable answer",
};

export const OUTCOMES = Object.entries(LABELS);

export function OutcomeBadge({ outcome, status }: { outcome: string; status: number | null }) {
  const label = LABELS[outcome] ?? outcome;
  return (
    <Badge variant={outcome === "ok" ? "secondary" : "destructive"} className="tabular-nums">
      {status !== null ? `${status} ` : ""}
      {label}
    </Badge>
  );
}

/** "https://host/path?query" -> "/path?query", for the list. */
export function shortUrl(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}` || url;
  } catch {
    return url;
  }
}
