/** From User management: which projects one person can open, and at what level (0007). */
import { NativeSelect } from "@/components/form";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { CompanyUser } from "@/features/users/types";
import { labelColour } from "@/lib/colours";

import { usePersonAccess, useProjects, useSetPersonAccess } from "../api";
import { LEVEL_HINTS, LEVEL_LABELS, type Level } from "../types";

const LEVELS: Level[] = ["view", "edit", "manage"];

export function ProjectAccessDialog({ user, onClose }: { user: CompanyUser; onClose: () => void }) {
  const access = usePersonAccess(user.id);
  const projects = useProjects({ archived: true });
  const set = useSetPersonAccess(user.id);
  const levels = new Map(access.data?.projects.map((p) => [p.project, p.level]));
  const name = user.name || user.email;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{name}'s projects</DialogTitle>
          <DialogDescription>
            {access.data?.manages_all
              ? `${name}'s role lets them open and change every project.`
              : "Choose what they can do in each project. Unshared projects stay hidden from them."}
          </DialogDescription>
        </DialogHeader>
        {!access.data || !projects.data ? (
          <Skeleton className="h-40" />
        ) : (
          <ul className="divide-y rounded-lg border">
            {projects.data.map((p) => {
              const level = levels.get(p.id);
              return (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2">
                  <span
                    className="size-3 shrink-0 rounded"
                    style={{ background: labelColour(p.colour) }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{p.name}</span>
                    {level && (
                      <span className="block truncate text-xs text-muted-foreground">
                        {LEVEL_HINTS[level]}
                      </span>
                    )}
                  </span>
                  <NativeSelect
                    aria-label={`Access to ${p.name}`}
                    className="w-36"
                    value={level ?? ""}
                    onChange={(e) =>
                      set.mutate({ project: p.id, level: (e.target.value || null) as Level | null })
                    }
                  >
                    <option value="">No access</option>
                    {LEVELS.map((l) => (
                      <option key={l} value={l}>
                        {LEVEL_LABELS[l]}
                      </option>
                    ))}
                  </NativeSelect>
                </li>
              );
            })}
            {!projects.data.length && (
              <li className="p-4 text-center text-sm text-muted-foreground">No projects yet.</li>
            )}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
