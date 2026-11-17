import { useState } from "react";

import { Field, FormError } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

import { useAddUser, useRoles, useUpdateUser } from "../api";
import type { CompanyUser } from "../types";
import { RolePicker } from "./role-picker";

/** Add a user (no `user`) or edit one. Mount it fresh each time it opens. */
export function UserDialog({ user, onClose }: { user: CompanyUser | null; onClose: () => void }) {
  const roles = useRoles();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [role, setRole] = useState<number | null>(user?.role.id ?? null);
  const add = useAddUser();
  const update = useUpdateUser();
  const saving = user ? update : add;

  const submit = () => {
    if (role === null) return;
    const fields = { name: name.trim(), role };
    if (user) update.mutate({ id: user.id, ...fields }, { onSuccess: onClose });
    else add.mutate({ email: email.trim(), ...fields }, { onSuccess: onClose });
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{user ? "Edit user" : "Add user"}</DialogTitle>
          <DialogDescription>
            {user
              ? "Change their name or role. A new role applies straight away."
              : "They'll get an email with a link to confirm their account."}
          </DialogDescription>
        </DialogHeader>

        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Field label="Name" htmlFor="user-name">
            <Input
              id="user-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
              autoFocus
              required
            />
          </Field>

          <Field
            label="Email"
            htmlFor="user-email"
            hint={user ? "An email address can't be changed." : undefined}
          >
            <Input
              id="user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
              disabled={!!user}
              required
            />
          </Field>

          {roles.data ? (
            <RolePicker roles={roles.data} value={role} onChange={setRole} />
          ) : (
            <Skeleton className="h-40 w-full" />
          )}

          <FormError error={saving.error ?? roles.error} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving.isPending || role === null}>
              {saving.isPending ? "Saving…" : user ? "Save" : "Send invitation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
