import { createFileRoute, useNavigate } from "@tanstack/react-router";

import { BoardScreen } from "@/features/boards/components/board-screen";

type Search = { view?: number; item?: number };

export const Route = createFileRoute("/_app/projects/$projectId/boards/$boardId")({
  validateSearch: (search: Record<string, unknown>): Search => ({
    view: Number(search.view) || undefined,
    item: Number(search.item) || undefined,
  }),
  component: BoardPage,
});

function BoardPage() {
  const { boardId } = Route.useParams();
  const { view, item } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  return (
    <BoardScreen
      key={boardId}
      boardId={Number(boardId)}
      viewId={view}
      itemId={item}
      onView={(id) => void navigate({ search: (s) => ({ ...s, view: id }) })}
      onItem={(id) => void navigate({ search: (s) => ({ ...s, item: id }) })}
    />
  );
}
