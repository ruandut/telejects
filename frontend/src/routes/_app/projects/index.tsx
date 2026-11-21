import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { FolderPlus } from "lucide-react";
import { useMemo, useState } from "react";

import { NativeSelect } from "@/components/form";
import { NoAccess } from "@/components/no-access";
import { SearchInput } from "@/components/search-input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { useProjects } from "@/features/projects/api";
import { ProjectDialog } from "@/features/projects/components/project-dialog";
import {
  LEVEL_LABELS,
  STATUS_COLOURS,
  STATUS_LABELS,
  type ProjectStatus,
} from "@/features/projects/types";
import { usePermission } from "@/features/realms/permissions";
import { labelColour } from "@/lib/colours";

export const Route = createFileRoute("/_app/projects/")({
  component: ProjectsPage,
});

function ProjectsPage() {
  const me = useMe();
  const canUse = usePermission("projects.view");
  const canCreate = usePermission("projects.manage");
  const [archived, setArchived] = useState(false);
  const projects = useProjects({ archived });
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (projects.data ?? []).filter(
      (p) =>
        (!status || p.status === status) &&
        (!needle || `${p.name} ${p.client}`.toLowerCase().includes(needle)),
    );
  }, [projects.data, search, status]);

  if (me.data && !canUse) return <NoAccess section="Projects" />;

  return (
    <div className="mx-auto w-full max-w-6xl p-4 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {canCreate ? "Every project in the company." : "The projects shared with you."}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <FolderPlus /> New project
          </Button>
        )}
      </div>
      <div className="mt-6 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
        <SearchInput
          label="Search projects"
          placeholder="Search by project or client"
          value={search}
          onChange={setSearch}
        />
        <NativeSelect
          aria-label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Archived"
          value={archived ? "1" : ""}
          onChange={(e) => setArchived(e.target.value === "1")}
        >
          <option value="">Current projects</option>
          <option value="1">Including archived</option>
        </NativeSelect>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />)}
        {shown.map((p) => (
          <Link
            key={p.id}
            to="/projects/$projectId"
            params={{ projectId: String(p.id) }}
            className="group grid gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-ring/60"
            style={{ borderTop: `4px solid ${labelColour(p.colour)}` }}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="truncate font-semibold group-hover:underline">{p.name}</h2>
                <p className="truncate text-sm text-muted-foreground">{p.client || "No client"}</p>
              </div>
              <span
                className="shrink-0 rounded-full px-2 py-0.5 text-xs text-white"
                style={{ background: labelColour(STATUS_COLOURS[p.status as ProjectStatus]) }}
              >
                {STATUS_LABELS[p.status]}
              </span>
            </div>
            {p.description && (
              <p className="line-clamp-2 text-sm text-muted-foreground">{p.description}</p>
            )}
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{p.owner_name ?? "No owner"}</span>
              <span>{LEVEL_LABELS[p.my_level]}</span>
            </div>
          </Link>
        ))}
      </div>
      {projects.data && !shown.length && (
        <div className="mt-4 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          {projects.data.length
            ? "No projects match."
            : canCreate
              ? "No projects yet. Create the first one."
              : "Nothing has been shared with you yet."}
        </div>
      )}
      {creating && (
        <ProjectDialog
          project={null}
          onClose={() => setCreating(false)}
          onCreated={(p) =>
            void navigate({ to: "/projects/$projectId", params: { projectId: String(p.id) } })
          }
        />
      )}
    </div>
  );
}
