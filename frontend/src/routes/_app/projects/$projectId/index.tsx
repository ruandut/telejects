import { createFileRoute, Navigate } from "@tanstack/react-router";

import { Skeleton } from "@/components/ui/skeleton";
import { useBoards } from "@/features/boards/api";

export const Route = createFileRoute("/_app/projects/$projectId/")({
  component: FirstBoard,
});

/** A project opens on its first board. */
function FirstBoard() {
  const { projectId } = Route.useParams();
  const boards = useBoards(Number(projectId));
  if (!boards.data) return <Skeleton className="h-64" />;
  const first = boards.data[0];
  if (!first)
    return <p className="text-sm text-muted-foreground">This project has no boards yet.</p>;
  return (
    <Navigate
      to="/projects/$projectId/boards/$boardId"
      params={{ projectId, boardId: String(first.id) }}
      replace
    />
  );
}
