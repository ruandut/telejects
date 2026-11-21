import { createFileRoute } from "@tanstack/react-router";

import { Dashboards } from "@/features/analytics/components/dashboards";
import { useProject } from "@/features/projects/api";

export const Route = createFileRoute("/_app/projects/$projectId/insights")({
  component: ProjectInsights,
});

function ProjectInsights() {
  const { projectId } = Route.useParams();
  const project = useProject(Number(projectId));
  return <Dashboards project={Number(projectId)} canChange={project.data?.my_level === "manage"} />;
}
