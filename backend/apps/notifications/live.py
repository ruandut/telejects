"""Live topic for notifications (see apps/realms/live.py): my unread count, sent when I get or
read one. Every subscriber's own count is worked out for them; nobody learns another's."""

from apps.realms.live import Topic

from .models import Notification


def _render(membership, subject, recipients):
    if membership.pk not in (recipients or []):
        return {"unread": None}
    unread = Notification.objects.in_realm(membership.realm_id).for_membership(membership).unread()
    return {"unread": unread.count()}


TOPICS = {"notifications": Topic(permission="projects.view", render=_render)}
