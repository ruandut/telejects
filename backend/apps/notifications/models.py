"""In-app notifications: what automations, mentions and assignments tell a person (0007).

A notification belongs to one person (a membership) in one company, and only they see it. It
links to what it's about by ids; opening the link goes through that app's own access checks.
"""

from django.db import models

from apps.realms.models import RealmMembership, TenantModel

from .querysets import NotificationQuerySet


class Notification(TenantModel):
    class Kind(models.TextChoices):
        MENTION = "mention", "Mention"
        ASSIGNED = "assigned", "Assigned"
        AUTOMATION = "automation", "Automation"

    recipient = models.ForeignKey(
        RealmMembership, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    # {"project": id, "board": id, "item": id}, whatever applies.
    link = models.JSONField(default=dict, blank=True)
    actor = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "read_at"])]
