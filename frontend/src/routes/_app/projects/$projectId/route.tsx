import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { BarChart3, MapPinned, MoreHorizontal, Plus, Settings, Trash2, Users } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useBoards } from "@/features/boards/api";
import { NewBoardDialog } from "@/features/boards/components/new-board-dialog";
import { useDeleteProject, useProject } from "@/features/projects/api";
import { ProjectDialog } from "@/features/projects/components/project-dialog";
import { STATUS_COLOURS, STATUS_LABELS } from "@/features/projects/types";
import { usePermission } from "@/features/realms/permissions";
import { labelColour } from "@/lib/colours";
import { ApiError } from "@/network/errors";

export const Route = createFileRoute("/_app/projects/$projectId")({
  component: ProjectLayout,
});

const tab =
  "-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-1 pb-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground data-[status=active]:border-primary data-[status=active]:text-foreground [&_svg]:size-4";

function ProjectLayout() {
  const { projectId } = Route.useParams();
  const id = Number(projectId);
  const project = useProject(id);
  const boards = useBoards(id);
  const remove = useDeleteProject(id);
  const canDelete = usePermission("projects.manage");
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [naming, setNaming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  if (project.error)
    return (
      <div className="mx-auto max-w-xl p-8 text-center">
        <h1 className="text-lg font-semibold">
          {project.error instanceof ApiError && project.error.status === 404
            ? "This project isn't here"
            : "Something went wrong"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          It may have been deleted, or it isn't shared with you.
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link to="/projects">All projects</Link>
        </Button>
      </div>
    );
  if (!project.data) return <Skeleton className="m-6 h-24" />;
  const p = project.data;
  const manage = p.my_level === "manage";

  return (
    <div className="w-full min-w-0 p-4 md:p-6">
      <div className="flex flex-wrap items-start gap-3">
        <span
          className="mt-1.5 size-4 shrink-0 rounded"
          style={{ background: labelColour(p.colour) }}
        />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{p.name}</h1>
          <p className="truncate text-sm text-muted-foreground">
            {[
              p.client,
              p.owner_name && `Owner: ${p.owner_name}`,
              p.end_date &&
                `Due ${new Date(`${p.end_date}T00:00:00`).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <span
          className="rounded-full px-2.5 py-0.5 text-xs text-white"
          style={{ background: labelColour(STATUS_COLOURS[p.status]) }}
        >
          {STATUS_LABELS[p.status]}
        </span>
        {manage && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Project options">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setEditing(true)}>
                <Settings /> Project settings
              </DropdownMenuItem>
              {canDelete && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setDeleting(true)}>
                    <Trash2 /> Delete project
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <nav
        className="mt-4 flex gap-x-5 overflow-x-auto border-b [scrollbar-width:none]"
        aria-label="Project"
      >
        {boards.data?.map((b) => (
          <Link
            key={b.id}
            to="/projects/$projectId/boards/$boardId"
            params={{ projectId, boardId: String(b.id) }}
            className={tab}
          >
            {b.feasibility_run && <MapPinned aria-label="From a feasibility run" />}
            {b.name}
            {b.item_count !== null && (
              <span className="rounded bg-muted px-1 text-[11px] tabular-nums">{b.item_count}</span>
            )}
          </Link>
        ))}
        {manage && (
          <button type="button" className={tab} onClick={() => setNaming(true)}>
            <Plus /> Board
          </button>
        )}
        <span className="flex-1" />
        <Link to="/projects/$projectId/insights" params={{ projectId }} className={tab}>
          <BarChart3 /> Insights
        </Link>
        <Link to="/projects/$projectId/access" params={{ projectId }} className={tab}>
          <Users /> Access
        </Link>
      </nav>
      <div className="mt-4 min-w-0">
        <Outlet />
      </div>
      {editing && <ProjectDialog project={p} onClose={() => setEditing(false)} />}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${p.name}?`}
        typeToConfirm={p.name}
        description="Its boards, items, automations and dashboards are deleted with it. This can't be undone; archive it from its settings to keep them."
        confirmLabel="Delete project"
        destructive
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => void navigate({ to: "/projects" }),
          })
        }
      />
      {naming && (
        <NewBoardDialog
          projectId={id}
          onClose={() => setNaming(false)}
          onCreated={(b) => {
            setNaming(false);
            void navigate({
              to: "/projects/$projectId/boards/$boardId",
              params: { projectId, boardId: String(b.id) },
            });
          }}
        />
      )}
    </div>
  );
}
