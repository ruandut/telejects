"""Live topics for boards (see apps/realms/live.py).

`board` sends the items that changed to whoever has the board open, built with the same
`item_rows` as `GET /api/boards/<id>/items/`, for the subscriber's own access: connect and
mirror values show only what they may see. Items gone or archived are sent as `removed`. A
change to the board itself (columns, groups, views) says "changed", and the tab refetches.
"""

from apps.realms.live import Topic

from .context import BoardContext
from .models import Board
from .serializers import item_rows, items_of


def _board(membership, board_id):
    return (
        Board.objects.in_realm(membership.realm_id)
        .visible_to(membership)
        .select_related("project")
        .by_id(board_id)
    )


def _authorize(membership, board_id) -> bool:
    return _board(membership, board_id) is not None


def _render(membership, board_id, item_ids):
    board = _board(membership, board_id)
    if board is None:
        return None
    ctx = BoardContext(board, membership)
    rows = item_rows(ctx, items_of(ctx, item_ids))
    present = {row["id"] for row in rows}
    return {"items": rows, "removed": [i for i in item_ids if i not in present]}


TOPICS = {
    "board": Topic(permission="projects.view", subject=True, authorize=_authorize, render=_render),
}
