"""The Logs section: a company's provider requests, newest first, searchable and filterable.

Everything is inside the request's company (`in_realm(request.realm)`), so another company's
entry is a 404. It needs `integrations.logs`. The log is written by the system and pruned by the
company's limit, so the API only reads.
"""

from datetime import datetime, time

from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import IntegrationLog
from .serializers import LogDetailSerializer, LogListSerializer

PAGE_SIZE = 50


def _int(value):
    return int(value) if value and str(value).isdigit() else None


def _day(value, end=False):
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except TypeError, ValueError:
        return None
    return timezone.make_aware(datetime.combine(day, time.max if end else time.min))


class LogViewSet(RealmScopedMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [InRealm, HasRealmPermission("integrations.logs")]
    queryset = IntegrationLog.objects.newest()
    serializer_class = LogDetailSerializer
    lookup_value_regex = r"\d+"

    def list(self, request):
        params = request.query_params
        entries = self.get_queryset()
        if (connection := _int(params.get("connection"))) is not None:
            entries = entries.filter(connection_id=connection)
        if operation := params.get("operation"):
            entries = entries.filter(operation=operation)
        if (run := _int(params.get("run"))) is not None:
            entries = entries.filter(run_id=run)
        if (check := _int(params.get("check"))) is not None:
            entries = entries.filter(check_id=check)
        if (sync := _int(params.get("sync"))) is not None:
            entries = entries.filter(sync_id=sync)
        if since := _day(params.get("from")):
            entries = entries.filter(created_at__gte=since)
        if until := _day(params.get("to"), end=True):
            entries = entries.filter(created_at__lte=until)
        entries = entries.with_outcome(params.get("outcome", ""))
        entries = entries.with_status(params.get("status", ""))
        entries = entries.search(params.get("search", ""))
        count = entries.count()
        page = max(_int(params.get("page")) or 1, 1)
        start = (page - 1) * PAGE_SIZE
        rows = entries[start : start + PAGE_SIZE]
        context = self.get_serializer_context()
        return Response(
            {
                "count": count,
                "page": page,
                "page_size": PAGE_SIZE,
                "results": LogListSerializer(rows, many=True, context=context).data,
            }
        )

    @action(detail=False, methods=["get"])
    def limits(self, request):
        """How many requests the company keeps, how many it has now, and the default."""
        return Response(
            {
                "max_entries": services.limit_for(request.realm.id),
                "default": services.default_limit(),
                "kept": IntegrationLog.objects.in_realm(request.realm).count(),
            }
        )
