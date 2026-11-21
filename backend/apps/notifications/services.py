"""Sending and reading notifications (0007). Callers name recipients by membership id; only
active members of the same company receive anything, and `allowed(membership)` lets the
caller drop people who may not see what it's about (a project they can't open)."""

from django.db import transaction
from django.utils import timezone

from apps.realms.events import publish
from apps.realms.models import RealmMembership

from .models import Notification

KEEP = 500  # per person; older ones are removed as new ones arrive


@transaction.atomic
def send(realm_id, recipients, *, kind, title, body="", link=None, actor="", allowed=None) -> list:
    people = RealmMembership.objects.in_realm(realm_id).active().filter(id__in=list(recipients))
    sent = []
    for person in people.select_related("role"):
        if allowed is not None and not allowed(person):
            continue
        sent.append(
            Notification.objects.create(
                realm_id=realm_id,
                recipient=person,
                kind=kind,
                title=title[:200],
                body=body[:500],
                link=link or {},
                actor=actor[:150],
            )
        )
        old = Notification.objects.in_realm(realm_id).for_membership(person)[KEEP:]
        stale = list(old.values_list("id", flat=True)[:200])
        if stale:
            Notification.objects.in_realm(realm_id).filter(id__in=stale).delete()
    if sent:
        publish(realm_id, "notifications", None, [n.recipient_id for n in sent])
    return sent


def mark_read(realm_id, membership, ids=None) -> int:
    rows = Notification.objects.in_realm(realm_id).for_membership(membership).unread()
    if ids is not None:
        rows = rows.filter(id__in=ids)
    count = rows.update(read_at=timezone.now())
    if count:
        publish(realm_id, "notifications", None, [membership.pk])
    return count
