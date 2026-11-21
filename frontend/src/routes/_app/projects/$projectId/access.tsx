import { createFileRoute } from "@tanstack/react-router";

import { Skeleton } from "@/components/ui/skeleton";
import { useProject } from "@/features/projects/api";
import { AccessPanel } from "@/features/projects/components/access-panel";

export const Route = createFileRoute("/_app/projects/$projectId/access")({
  component: ProjectAccess,
});

function ProjectAccess() {
  const { projectId } = Route.useParams();
  const project = useProject(Number(projectId));
  return project.data ? <AccessPanel project={project.data} /> : <Skeleton className="h-48" />;
}
