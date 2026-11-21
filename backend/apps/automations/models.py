"""Automations: "When <trigger>, and only if <conditions>, do <actions>" on a board (0007).

The trigger, conditions and actions are JSON, checked by recipes.py, the one list of what an
automation can do. `delay` makes the actions wait ("after 2 days"). Every time one fires it
leaves an AutomationRun: done, failed (with why), skipped, or scheduled for later.
"""

from django.db import models

from apps.boards.models import Board, Item
from apps.realms.models import RealmMembership, TenantModel

from .querysets import AutomationQuerySet, RunQuerySet


class Automation(TenantModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    trigger = models.JSONField()
    conditions = models.JSONField(default=list, blank=True)
    actions = models.JSONField(default=list)
    # {"amount": 2, "unit": "minutes"|"hours"|"days"} or null for straight away.
    delay = models.JSONField(null=True, blank=True)
    # Timer bookkeeping: the last schedule occurrence fired ("2026-11-23T08:00").
    state = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        RealmMembership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    run_count = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    objects = AutomationQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.name


class AutomationRun(TenantModel):
    class Status(models.TextChoices):
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    automation = models.ForeignKey(Automation, on_delete=models.CASCADE, related_name="runs")
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    item_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    message = models.CharField(max_length=500, blank=True)
    # Fires once per item per key: "date:2026-11-23", "schedule:2026-11-23T08:00".
    trigger_key = models.CharField(max_length=60, blank=True)
    # Who set it off (for "the person who changed it" in notify), and how deep in a chain.
    by = models.ForeignKey(
        RealmMembership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    depth = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = RunQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["automation", "item", "trigger_key"],
                condition=~models.Q(trigger_key=""),
                name="automation_fires_once_per_key",
            )
        ]
        indexes = [models.Index(fields=["status", "due_at"])]
