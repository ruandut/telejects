from datetime import timedelta

from django.utils import timezone

from apps.realms.querysets import TenantQuerySet

PRESENCE_SECONDS = 45


class PresenceQuerySet(TenantQuerySet):
    def of_board(self, board):
        return self.filter(board_id=board.pk)

    def fresh(self):
        return self.filter(last_seen__gte=timezone.now() - timedelta(seconds=PRESENCE_SECONDS))

    def stale(self):
        return self.filter(last_seen__lt=timezone.now() - timedelta(seconds=PRESENCE_SECONDS))
