"""Who is on a board right now, and which cell they're in (0007).

Each open tab sends a heartbeat every 20 seconds and when it focuses a cell. A tab not heard from
for PRESENCE_SECONDS has left; a minutely task removes it and tells the board.
"""

from django.db import models

from apps.boards.models import Board
from apps.realms.models import RealmMembership, TenantModel

from .querysets import PresenceQuerySet


class BoardPresence(TenantModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="+")
    membership = models.ForeignKey(RealmMembership, on_delete=models.CASCADE, related_name="+")
    tab = models.CharField(max_length=40)
    item_id = models.PositiveIntegerField(null=True, blank=True)
    column_key = models.CharField(max_length=40, blank=True)
    last_seen = models.DateTimeField()

    objects = PresenceQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["board", "membership", "tab"], name="one_presence_per_tab"
            )
        ]
        indexes = [models.Index(fields=["board", "last_seen"])]
