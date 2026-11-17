import { Badge } from "@/components/ui/badge";

import type { Connection } from "../types";

export function HealthBadge({ connection }: { connection: Connection }) {
  if (!connection.enabled) return <Badge variant="outline">Off</Badge>;
  if (connection.health === "ok") return <Badge variant="secondary">Connected</Badge>;
  if (connection.health === "failing") return <Badge variant="destructive">Failing</Badge>;
  return <Badge variant="outline">Checking…</Badge>;
}
