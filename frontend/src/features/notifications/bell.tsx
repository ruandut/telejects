/** The bell in the header: what automations, mentions and assignments told me, live. */
import { useNavigate } from "@tanstack/react-router";
import { AtSign, Bell, Bot, UserPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { usePermission } from "@/features/realms/permissions";
import { cn } from "@/lib/utils";

import { useMarkRead, useNotifications, type Notification } from "./api";

const ICONS = { mention: AtSign, assigned: UserPlus, automation: Bot };

function ago(at: string) {
  const minutes = Math.round((Date.now() - new Date(at).getTime()) / 60000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}h`;
  return `${Math.round(minutes / 1440)}d`;
}

export function NotificationBell() {
  const enabled = usePermission("projects.view");
  const notifications = useNotifications(enabled);
  const markRead = useMarkRead();
  const navigate = useNavigate();
  if (!enabled) return null;
  const unread = notifications.data?.unread ?? 0;

  const open = (n: Notification) => {
    if (!n.read_at) markRead.mutate([n.id]);
    if (n.link.project && n.link.board)
      void navigate({
        to: "/projects/$projectId/boards/$boardId",
        params: { projectId: String(n.link.project), boardId: String(n.link.board) },
        search: { item: n.link.item },
      });
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        >
          <Bell />
          {unread > 0 && (
            <span className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-4 font-semibold text-white tabular-nums">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-2rem))] gap-0 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <p className="font-medium">Notifications</p>
          {unread > 0 && (
            <button
              type="button"
              className="text-xs text-primary hover:underline"
              onClick={() => markRead.mutate(undefined)}
            >
              Mark all read
            </button>
          )}
        </div>
        <ul className="max-h-[60dvh] overflow-y-auto">
          {notifications.data?.results.map((n) => {
            const Icon = ICONS[n.kind] ?? Bell;
            return (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => open(n)}
                  className={cn(
                    "flex w-full gap-3 border-b px-3 py-2.5 text-left hover:bg-muted",
                    !n.read_at && "bg-accent/40",
                  )}
                >
                  <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-sm", !n.read_at && "font-medium")}>
                      {n.title}
                    </span>
                    {n.body && (
                      <span className="line-clamp-2 block text-xs text-muted-foreground">
                        {n.body}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {ago(n.created_at)}
                  </span>
                </button>
              </li>
            );
          })}
          {notifications.data?.results.length === 0 && (
            <li className="p-6 text-center text-sm text-muted-foreground">You're all caught up.</li>
          )}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
