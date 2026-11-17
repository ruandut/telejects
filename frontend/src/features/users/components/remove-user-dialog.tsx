import { useState } from "react";

import { Field, FormError, NativeSelect } from "@/components/form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { useRemoveUser } from "../api";
import type { CompanyUser } from "../types";

const ADMIN = "admin";

/**
 * Confirm removing a user, or cancelling their invitation. A company always has an Admin, so
 * removing its only one means choosing who takes over first.
 */
export function RemoveUserDialog({
  user,
  users,
  onClose,
}: {
  user: CompanyUser;
  users: CompanyUser[];
  onClose: () => void;
}) {
  const remove = useRemoveUser();
  const [successor, setSuccessor] = useState("");

  const invited = user.status === "invited";
  const others = users.filter((other) => other.id !== user.id && other.status === "active");
  const isLastAdmin =
    !invited && user.role.key === ADMIN && !others.some((other) => other.role.key === ADMIN);
  const blocked = !invited && others.length === 0;
  const who = user.is_me ? "yourself" : user.name || user.email;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{invited ? `Cancel ${who}'s invitation?` : `Remove ${who}?`}</DialogTitle>
          <DialogDescription>
            {blocked
              ? "This is the only active user. Add someone else and wait for them to confirm before removing this one."
              : invited
                ? "The link in their email will stop working."
                : user.is_me
                  ? "You'll lose access to this company straight away."
                  : "They'll lose access straight away. Their history is kept."}
          </DialogDescription>
        </DialogHeader>

        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            remove.mutate(
              { user, newAdmin: isLastAdmin ? Number(successor) : null },
              { onSuccess: onClose },
            );
          }}
        >
          {isLastAdmin && !blocked && (
            <Field
              label="Who takes over as Admin?"
              htmlFor="successor"
              hint="A company always needs an Admin."
            >
              <NativeSelect
                id="successor"
                value={successor}
                onChange={(e) => setSuccessor(e.target.value)}
                required
              >
                <option value="" disabled>
                  Choose a user
                </option>
                {others.map((other) => (
                  <option key={other.id} value={other.id}>
                    {other.name || other.email}
                  </option>
                ))}
              </NativeSelect>
            </Field>
          )}

          <FormError error={remove.error} />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Keep
            </Button>
            <Button type="submit" variant="destructive" disabled={blocked || remove.isPending}>
              {remove.isPending ? "Working…" : invited ? "Cancel invitation" : "Remove"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
