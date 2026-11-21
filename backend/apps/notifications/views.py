"""My notifications (0007). Always only the signed-in person's own, in the request's company."""

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import InRealm

from . import services
from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(RealmScopedMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [InRealm]
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return super().get_queryset().for_membership(self.request.membership)

    def list(self, request):
        rows = self.get_queryset()
        if request.query_params.get("unread") == "1":
            rows = rows.unread()
        return Response(
            {
                "unread": self.get_queryset().unread().count(),
                "results": NotificationSerializer(rows[:50], many=True).data,
            }
        )

    @action(detail=False, methods=["post"])
    def read(self, request):
        """{"ids": [...]} marks those read; no ids marks every one read."""
        ids = request.data.get("ids")
        if ids is not None:
            ids = [int(i) for i in ids if str(i).isdigit()][:200]
        services.mark_read(request.realm.id, request.membership, ids)
        return Response({"unread": self.get_queryset().unread().count()})
