"""Live topic for presence (see apps/realms/live.py): who is on a board, sent to whoever has
it open, after checking they may still open it."""

from apps.boards.models import Board
from apps.realms.live import Topic

from . import services


def _board(membership, board_id):
    return Board.objects.in_realm(membership.realm_id).visible_to(membership).by_id(board_id)


def _authorize(membership, board_id) -> bool:
    return _board(membership, board_id) is not None


def _render(membership, board_id, items):
    board = _board(membership, board_id)
    return None if board is None else {"people": services.present(board)}


TOPICS = {
    "board_presence": Topic(
        permission="projects.view", subject=True, authorize=_authorize, render=_render
    )
}
