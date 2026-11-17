"""Live topic for the Logs section (see apps/realms/live.py): new entries, rendered with the
list's serializer for the subscriber's own company."""

from apps.realms.live import Topic

from .models import IntegrationLog
from .serializers import LogListSerializer


def _render(membership, subject, ids):
    entries = IntegrationLog.objects.in_realm(membership.realm_id).filter(id__in=ids).newest()
    return {"entries": LogListSerializer(entries, many=True).data}


TOPICS = {"integration_logs": Topic(permission="integrations.logs", render=_render)}
