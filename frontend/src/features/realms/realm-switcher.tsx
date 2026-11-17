import { Link } from "@tanstack/react-router";
import { Check, ChevronsUpDown } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { Mark } from "@/components/wordmark";
import { useMe } from "@/features/auth/api";

import { enterRealm } from "./realm-gate";

/** The company this tab works in. Someone in more than one switches here. */
export function RealmSwitcher({ onNavigate }: { onNavigate: () => void }) {
  const me = useMe().data;
  const current = me?.realm;
  const realms = me?.realms ?? [];

  const label = (
    <>
      <Mark aria-hidden className="size-8 shrink-0 text-sidebar-primary" />
      <div className="grid min-w-0 flex-1 text-left text-sm leading-tight">
        <span className="truncate font-semibold">{current?.name ?? "Telejects"}</span>
        <span className="truncate text-xs text-muted-foreground">
          {current?.role.name ?? "No company"}
        </span>
      </div>
    </>
  );

  if (realms.length < 2) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton asChild size="lg" tooltip={current?.name ?? "Telejects"}>
            <Link to="/" onClick={onNavigate}>
              {label}
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" tooltip={current?.name ?? "Switch company"}>
              {label}
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="bottom" align="start" className="w-64">
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Companies
            </DropdownMenuLabel>
            {realms.map((realm) => (
              <DropdownMenuItem
                key={realm.id}
                onSelect={() => {
                  onNavigate();
                  if (realm.id !== current?.id) enterRealm(realm.id);
                }}
              >
                <span className="min-w-0 flex-1 truncate">{realm.name}</span>
                {realm.id === current?.id && <Check aria-label="Current company" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
