import { Link, useMatchRoute, useNavigate } from "@tanstack/react-router";
import {
  ChartPie,
  ChevronRight,
  ChevronsUpDown,
  CodeXml,
  FolderKanban,
  LayoutDashboard,
  MapPinned,
  Plug,
  ScrollText,
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
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { signOut, useMe } from "@/features/auth/api";
import { useProjects } from "@/features/projects/api";
import { labelColour } from "@/lib/colours";
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

/** The menu, in sections. A section with nothing I may open is left out. */
const SECTIONS: { label: string; items: NavItem[] }[] = [
  {
    label: "Work",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
      { to: "/projects", label: "Projects", icon: FolderKanban, needs: "projects.view" },
      { to: "/portfolio", label: "Portfolio", icon: ChartPie, needs: "projects.view" },
      {
        to: "/feasibilities",
        label: "Feasibilities",
        icon: MapPinned,
        needs: "feasibilities.view",
      },
    ],
  },
  {
    label: "Providers",
    items: [
      { to: "/integrations", label: "Integrations", icon: Plug, needs: "integrations.view" },
      { to: "/logs", label: "Logs", icon: ScrollText, needs: "integrations.logs" },
    ],
  },
  {
    label: "Company",
    items: [
      { to: "/users", label: "User management", icon: Users, needs: "users.view" },
      { to: "/developers", label: "Developers", icon: CodeXml, needs: "api_clients.manage" },
    ],
  },
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
  const sections = SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.needs || permissions.includes(item.needs)),
  })).filter((section) => section.items.length);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <RealmSwitcher onNavigate={closeOnMobile} />
      </SidebarHeader>
      <SidebarContent>
        {sections.map((section) => (
          <SidebarGroup key={section.label}>
            <SidebarGroupLabel>{section.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map((item) =>
                  item.to === "/projects" ? (
                    <ProjectsItem
                      key={item.to}
                      item={item}
                      active={!!matchRoute({ to: item.to, fuzzy: true })}
                      onNavigate={closeOnMobile}
                    />
                  ) : (
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
                  ),
                )}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

/** Projects, with the ones I can open listed under it, like monday.com's workspace boards. */
function ProjectsItem({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate: () => void;
}) {
  const projects = useProjects();
  const matchRoute = useMatchRoute();
  const list = (projects.data ?? []).slice(0, 12);
  return (
    <Collapsible asChild defaultOpen={active} className="group/collapsible">
      <SidebarMenuItem>
        <SidebarMenuButton asChild isActive={active} tooltip={item.label}>
          <Link to={item.to} onClick={onNavigate} activeOptions={{ exact: true }}>
            <item.icon className="size-4" />
            <span>{item.label}</span>
          </Link>
        </SidebarMenuButton>
        {list.length > 0 && (
          <>
            <CollapsibleTrigger
              className="absolute top-1.5 right-1 flex size-5 items-center justify-center rounded-md text-sidebar-foreground/70 hover:bg-sidebar-accent group-data-[collapsible=icon]:hidden"
              aria-label="Show projects"
            >
              <ChevronRight className="size-4 transition-transform group-data-[state=open]/collapsible:rotate-90" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarMenuSub>
                {list.map((project) => (
                  <SidebarMenuSubItem key={project.id}>
                    <SidebarMenuSubButton
                      asChild
                      isActive={
                        !!matchRoute({
                          to: "/projects/$projectId",
                          params: { projectId: String(project.id) },
                          fuzzy: true,
                        })
                      }
                    >
                      <Link
                        to="/projects/$projectId"
                        params={{ projectId: String(project.id) }}
                        onClick={onNavigate}
                      >
                        <span
                          className="size-2 shrink-0 rounded-sm"
                          style={{ background: labelColour(project.colour) }}
                        />
                        <span className="truncate">{project.name}</span>
                      </Link>
                    </SidebarMenuSubButton>
                  </SidebarMenuSubItem>
                ))}
              </SidebarMenuSub>
            </CollapsibleContent>
          </>
        )}
      </SidebarMenuItem>
    </Collapsible>
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
              <span className="min-w-0 flex-1 truncate font-medium group-data-[collapsible=icon]:hidden">
                {name}
              </span>
              <ChevronsUpDown className="ml-auto size-4 group-data-[collapsible=icon]:hidden" />
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
