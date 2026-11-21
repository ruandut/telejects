/** Rapid's -1: price on request. */
export const ON_REQUEST = -1;

const rand = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR" });

/** "R 1 234,50", or "On request" for -1. */
export function cost(value: string): string {
  const amount = Number(value);
  return amount === ON_REQUEST ? "On request" : rand.format(amount);
}

/** "100 Mbps", or "100/50 Mbps" when upload differs. */
export function speed(down: number | null, up: number | null): string {
  if (down === null) return "—";
  return down === up || up === null ? `${down} Mbps` : `${down}/${up} Mbps`;
}
