import { Ellipsis, FolderKey, Mail, Pencil, Trash2, UserX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { useResendInvitation } from "../api";
import type { CompanyUser } from "../types";

type Actions = {
  /** Null when I may only look. */
  onEdit: ((user: CompanyUser) => void) | null;
  onRemove: ((user: CompanyUser) => void) | null;
  /** Which projects they can open (0007); null without `projects.manage`. */
  onProjects: ((user: CompanyUser) => void) | null;
};

const joined = new Intl.DateTimeFormat("en-ZA", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** A table on wider screens; a list of cards at phone width, so nothing scrolls sideways. */
export function UserTable({ users, ...actions }: { users: CompanyUser[] } & Actions) {
  if (users.length === 0) {
    return (
      <p className="rounded-xl border bg-card p-6 text-center text-sm text-muted-foreground">
        Nobody matches.
      </p>
    );
  }
  return (
    <>
      <div className="hidden rounded-xl border bg-card md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="max-w-72 pl-4">
                  <Person user={user} />
                </TableCell>
                <TableCell>{user.role.name}</TableCell>
                <TableCell>
                  <Status user={user} />
                </TableCell>
                <TableCell className="text-muted-foreground tabular-nums">
                  {joined.format(new Date(user.joined_at))}
                </TableCell>
                <TableCell>
                  <RowMenu user={user} {...actions} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <ul className="grid gap-2 md:hidden">
        {users.map((user) => (
          <li key={user.id} className="flex items-start gap-3 rounded-xl border bg-card p-4">
            <div className="min-w-0 flex-1">
              <Person user={user} />
              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="secondary">{user.role.name}</Badge>
                <Status user={user} />
              </div>
            </div>
            <RowMenu user={user} {...actions} />
          </li>
        ))}
      </ul>
    </>
  );
}

function Person({ user }: { user: CompanyUser }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span
        aria-hidden
        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-primary"
      >
        {(user.name || user.email).charAt(0).toUpperCase()}
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium">{user.name || user.email}</span>
          {user.is_me && <Badge variant="outline">You</Badge>}
        </div>
        <p className="truncate text-sm text-muted-foreground">{user.email}</p>
      </div>
    </div>
  );
}

function Status({ user }: { user: CompanyUser }) {
  return user.status === "invited" ? (
    <Badge variant="outline" className="border-brand-accent/60 text-brand-accent">
      Invited
    </Badge>
  ) : (
    <span className="text-sm text-muted-foreground">Active</span>
  );
}

function RowMenu({ user, onEdit, onRemove, onProjects }: { user: CompanyUser } & Actions) {
  const resend = useResendInvitation();
  if (!onEdit && !onProjects) return null;
  const invited = user.status === "invited";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Actions for ${user.name || user.email}`}>
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {onEdit && (
          <DropdownMenuItem onSelect={() => onEdit(user)}>
            <Pencil /> Edit name or role
          </DropdownMenuItem>
        )}
        {onProjects && (
          <DropdownMenuItem onSelect={() => onProjects(user)}>
            <FolderKey /> Project access
          </DropdownMenuItem>
        )}
        {onEdit && invited && (
          <DropdownMenuItem onSelect={() => resend.mutate(user)}>
            <Mail /> Resend invitation
          </DropdownMenuItem>
        )}
        {onRemove && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => onRemove(user)}>
              {invited ? <UserX /> : <Trash2 />} {invited ? "Cancel invitation" : "Remove"}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
