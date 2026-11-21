import { createFileRoute } from "@tanstack/react-router";
import { UserPlus } from "lucide-react";
import { useMemo, useState } from "react";

import { NativeSelect } from "@/components/form";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { usePermission } from "@/features/realms/permissions";
import { useRoles, useUsers } from "@/features/users/api";
import { RemoveUserDialog } from "@/features/users/components/remove-user-dialog";
import { UserDialog } from "@/features/users/components/user-dialog";
import { UserTable } from "@/features/users/components/user-table";
import { ProjectAccessDialog } from "@/features/projects/components/person-access-dialog";
import type { CompanyUser } from "@/features/users/types";

export const Route = createFileRoute("/_app/users/")({
  component: UsersPage,
});

type Open = { kind: "add" } | { kind: "edit" | "remove" | "projects"; user: CompanyUser } | null;

function UsersPage() {
  const me = useMe();
  const canView = usePermission("users.view");
  const canManage = usePermission("users.manage");
  const canShare = usePermission("projects.manage");

  // The server refuses these requests too; this just says so nicely.
  if (me.data && !canView) {
    return (
      <div className="mx-auto w-full max-w-xl p-4 md:p-8">
        <div className="rounded-xl border bg-card p-6 text-center">
          <h1 className="text-lg font-semibold">You don't have access to User management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Ask one of your company's Admins if something needs to change.
          </p>
        </div>
      </div>
    );
  }
  return (
    <UserManagement companyName={me.data?.realm?.name} canManage={canManage} canShare={canShare} />
  );
}

function UserManagement({
  companyName,
  canManage,
  canShare,
}: {
  companyName: string | undefined;
  canManage: boolean;
  canShare: boolean;
}) {
  const users = useUsers();
  const roles = useRoles();
  const [open, setOpen] = useState<Open>(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (users.data ?? []).filter(
      (user) =>
        (!roleFilter || String(user.role.id) === roleFilter) &&
        (!statusFilter || user.status === statusFilter) &&
        (!needle || `${user.name} ${user.email}`.toLowerCase().includes(needle)),
    );
  }, [users.data, search, roleFilter, statusFilter]);

  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">User management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            The people in {companyName ?? "your company"} and their roles.
          </p>
        </div>
        {canManage && (
          <Button onClick={() => setOpen({ kind: "add" })}>
            <UserPlus /> Add user
          </Button>
        )}
      </div>

      <div className="mt-6 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
        <SearchInput
          label="Search users"
          placeholder="Search by name or email"
          value={search}
          onChange={setSearch}
        />
        <NativeSelect
          aria-label="Filter by role"
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="">All roles</option>
          {roles.data?.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="invited">Invited</option>
        </NativeSelect>
      </div>

      <div className="mt-4">
        {users.data ? (
          <UserTable
            users={shown}
            onEdit={canManage ? (user) => setOpen({ kind: "edit", user }) : null}
            onRemove={canManage ? (user) => setOpen({ kind: "remove", user }) : null}
            onProjects={canShare ? (user) => setOpen({ kind: "projects", user }) : null}
          />
        ) : users.error ? (
          <p role="alert" className="text-sm text-destructive">
            {users.error.message}
          </p>
        ) : (
          <div className="grid gap-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}
      </div>

      {open?.kind === "add" && <UserDialog user={null} onClose={() => setOpen(null)} />}
      {open?.kind === "edit" && <UserDialog user={open.user} onClose={() => setOpen(null)} />}
      {open?.kind === "projects" && (
        <ProjectAccessDialog user={open.user} onClose={() => setOpen(null)} />
      )}
      {open?.kind === "remove" && (
        <RemoveUserDialog user={open.user} users={users.data ?? []} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
