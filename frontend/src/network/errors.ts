export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(describe(body) ?? `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
}

/** First human-readable message out of a DRF error body. */
function describe(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  for (const [field, value] of Object.entries(body as Record<string, unknown>)) {
    const text: unknown = Array.isArray(value) ? value[0] : value;
    if (typeof text !== "string") {
      // Nested serializers report per-row errors, e.g. {lines: [{}, {amount: ["…"]}]}.
      const nested = describe(value);
      if (nested) return nested;
      continue;
    }
    return field === "detail" || field === "non_field_errors"
      ? text
      : `${field.replaceAll("_", " ")}: ${text}`;
  }
  return null;
}
