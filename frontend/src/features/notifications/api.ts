import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useLive } from "@/features/realms/live";
import { api } from "@/network/client";

export type Notification = {
  id: number;
  kind: "mention" | "assigned" | "automation";
  title: string;
  body: string;
  link: { project?: number; board?: number; item?: number };
  actor: string;
  created_at: string;
  read_at: string | null;
};

const KEY = ["notifications"];

export function useNotifications(enabled: boolean) {
  const client = useQueryClient();
  useLive(enabled ? "notifications" : null, null, (message) => {
    if (message.type === "data" && (message.data as { unread: number | null }).unread === null)
      return;
    void client.invalidateQueries({ queryKey: KEY });
  });
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<{ unread: number; results: Notification[] }>("/api/notifications/"),
    enabled,
  });
}

export function useMarkRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids?: number[]) =>
      api<{ unread: number }>("/api/notifications/read/", {
        method: "POST",
        body: JSON.stringify(ids ? { ids } : {}),
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: KEY }),
  });
}
