import { cn } from "@/lib/utils";

import type { Role } from "../types";

/** The company's roles as a list of choices, each saying what it's for. */
export function RolePicker({
  roles,
  value,
  onChange,
}: {
  roles: Role[];
  value: number | null;
  onChange: (roleId: number) => void;
}) {
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-2 text-sm font-medium">Role</legend>
      {roles.map((role) => {
        const checked = role.id === value;
        return (
          <label
            key={role.id}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors has-focus-visible:ring-3 has-focus-visible:ring-ring/50",
              checked ? "border-primary bg-accent" : "hover:bg-muted",
            )}
          >
            <input
              type="radio"
              name="role"
              value={role.id}
              checked={checked}
              onChange={() => onChange(role.id)}
              className="mt-0.5 accent-primary"
              required
            />
            <span className="grid gap-0.5">
              <span className="text-sm font-medium">{role.name}</span>
              <span className="text-xs text-muted-foreground">{role.description}</span>
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}
