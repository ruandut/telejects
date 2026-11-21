"""Presence: heartbeats, leaving, and the sweep of tabs that went quiet (0007)."""

from django.db import transaction
from django.utils import timezone

from apps.realms.events import publish

from .models import BoardPresence


def _changed(realm_id, board_id):
    # An empty list (not None): the socket then sends who is there, not just "changed".
    publish(realm_id, "board_presence", board_id, [])


@transaction.atomic
def heartbeat(board, membership, tab: str, item_id=None, column_key="") -> None:
    rows = BoardPresence.objects.in_realm(board.realm_id)
    row = rows.select_for_update().filter(board=board, membership=membership, tab=tab).first()
    now = timezone.now()
    column_key = (column_key or "")[:40] if item_id else ""
    if row is None:
        BoardPresence.objects.create(
            realm_id=board.realm_id,
            board=board,
            membership=membership,
            tab=tab[:40],
            item_id=item_id,
            column_key=column_key,
            last_seen=now,
        )
        _changed(board.realm_id, board.pk)
        return
    moved = (row.item_id, row.column_key) != (item_id, column_key)
    row.item_id, row.column_key, row.last_seen = item_id, column_key, now
    row.save(update_fields=["item_id", "column_key", "last_seen"])
    if moved:
        _changed(board.realm_id, board.pk)


@transaction.atomic
def leave(board, membership, tab: str) -> None:
    gone, _ = (
        BoardPresence.objects.in_realm(board.realm_id)
        .filter(board=board, membership=membership, tab=tab)
        .delete()
    )
    if gone:
        _changed(board.realm_id, board.pk)


def present(board) -> list[dict]:
    """Who is on the board: one entry per person, with the cell of their latest tab."""
    rows = (
        BoardPresence.objects.in_realm(board.realm_id)
        .of_board(board)
        .fresh()
        .select_related("membership__user")
        .order_by("-last_seen")
    )
    people: dict[int, dict] = {}
    for row in rows:
        if row.membership_id in people or not row.membership.is_active:
            continue
        people[row.membership_id] = {
            "id": row.membership_id,
            "name": row.membership.display_name,
            "item": row.item_id,
            "column": row.column_key or None,
        }
    return sorted(people.values(), key=lambda p: p["name"].lower())


@transaction.atomic
def sweep() -> int:
    """Remove tabs that stopped sending heartbeats, in every company, and tell their boards."""
    stale = BoardPresence.objects.across_realms().stale()
    boards = set(stale.values_list("realm_id", "board_id"))
    count, _ = stale.delete()
    for realm_id, board_id in boards:
        _changed(realm_id, board_id)
    return count
