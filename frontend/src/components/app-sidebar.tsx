import { Link, useMatchRoute, useNavigate } from "@tanstack/react-router";
import {
  ChevronsUpDown,
  LayoutDashboard,
  LogOut,
  UserCog,
  Users,
  type LucideIcon,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { signOut, useMe } from "@/features/auth/api";
import type { Permission } from "@/features/auth/types";
import { RealmSwitcher } from "@/features/realms/realm-switcher";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
  /** Shown only to people with this permission in the tab's company. */
  needs?: Permission;
};

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/users", label: "User management", icon: Users, needs: "users.view" },
];

/** On a phone the sidebar is a drawer over the page, so choosing something should dismiss it. */
function useCloseOnMobile() {
  const { isMobile, setOpenMobile } = useSidebar();
  return () => {
    if (isMobile) setOpenMobile(false);
  };
}

export function AppSidebar() {
  const matchRoute = useMatchRoute();
  const closeOnMobile = useCloseOnMobile();
  const permissions = useMe().data?.realm?.permissions ?? [];
  const shown = NAV.filter((item) => !item.needs || permissions.includes(item.needs));

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <RealmSwitcher onNavigate={closeOnMobile} />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {shown.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    asChild
                    isActive={!!matchRoute({ to: item.to, fuzzy: !item.exact })}
                    tooltip={item.label}
                  >
                    <Link to={item.to} onClick={closeOnMobile}>
                      <item.icon className="size-4" />
                      <span>{item.label}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

function UserMenu() {
  const me = useMe();
  const navigate = useNavigate();
  const closeOnMobile = useCloseOnMobile();
  const name = me.data?.name ?? "…";

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" tooltip={name}>
              <div
                aria-hidden
                className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted font-medium uppercase"
              >
                {me.data?.name.charAt(0) ?? "·"}
              </div>
              <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-60">
            <DropdownMenuLabel className="grid gap-0.5">
              <span className="truncate font-medium">{name}</span>
              <span className="truncate text-xs font-normal text-muted-foreground">
                {me.data?.email}
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => {
                closeOnMobile();
                void navigate({ to: "/account" });
              }}
            >
              <UserCog /> My settings
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                closeOnMobile();
                signOut();
                void navigate({ to: "/login" });
              }}
            >
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
