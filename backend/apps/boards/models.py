"""Boards: the table of a project's work (0007). A board has groups of items (rows) and typed
columns; each item keeps its values as one JSON object keyed by column key (column_types.py).

Everything here hangs off a project and is reached through `visible_to(membership)` after
`in_realm`, so someone who can't open the project can't reach its boards, items or updates.
Only services.py changes these rows.
"""

from django.conf import settings
from django.db import models

from apps.feasibilities.models import FeasibilityRun
from apps.projects.models import Project
from apps.realms.models import RealmMembership, TenantModel

from .column_types import COLOURS, TYPES
from .querysets import (
    ActivityQuerySet,
    BoardChildQuerySet,
    BoardQuerySet,
    ItemQuerySet,
    ItemUpdateQuerySet,
)


class Board(TenantModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="boards")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    position = models.FloatField(default=0)
    # Which status column says an item is done, and which date column is its due date. Either
    # may be empty: the first status column counts then, and nothing is ever overdue.
    status_column = models.CharField(max_length=40, blank=True)
    due_column = models.CharField(max_length=40, blank=True)
    item_seq = models.PositiveIntegerField(default=0)
    # The feasibility run the board's items were made from, if any (0007).
    feasibility_run = models.ForeignKey(
        FeasibilityRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BoardQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["realm", "id"], name="board_realm_id_pair")]

    def __str__(self):
        return self.name


class Group(TenantModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(max_length=120)
    colour = models.CharField(max_length=20, default="blue", choices=[(c, c) for c in COLOURS])
    position = models.FloatField(default=0)

    objects = BoardChildQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["realm", "id"], name="group_realm_id_pair")]

    def __str__(self):
        return self.name


class Column(TenantModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    # Where the column's values live in each item's `values`. Never changes, never reused.
    key = models.CharField(max_length=40)
    title = models.CharField(max_length=80)
    type = models.CharField(max_length=20, choices=[(k, t.label) for k, t in TYPES.items()])
    description = models.CharField(max_length=300, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    position = models.FloatField(default=0)
    width = models.PositiveSmallIntegerField(default=160)

    objects = BoardChildQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["board", "key"], name="column_key_unique_on_board")
        ]

    def __str__(self):
        return self.title


class Item(TenantModel):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="items")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="items")
    number = models.PositiveIntegerField()  # per board: the item's ID
    name = models.CharField(max_length=255)
    position = models.FloatField(default=0)
    values = models.JSONField(default=dict, blank=True)
    # Kept by services from the board's status column, for progress and charts.
    done = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        RealmMembership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    objects = ItemQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "id"], name="item_realm_id_pair"),
            models.UniqueConstraint(fields=["board", "number"], name="item_number_unique_on_board"),
        ]
        indexes = [models.Index(fields=["board", "archived_at"])]

    def __str__(self):
        return self.name


class ItemUpdate(TenantModel):
    """A message on an item, like monday.com's Updates: what's happening, with @mentions."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(
        RealmMembership, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField(max_length=10000)
    mentions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    objects = ItemUpdateQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]


class ItemActivity(TenantModel):
    """One change to an item: who (a person or an automation) did what, with the values before
    and after."""

    class Kind(models.TextChoices):
        CREATED = "created", "Created"
        VALUE = "value", "Changed a value"
        NAME = "name", "Renamed"
        MOVED = "moved", "Moved"
        ARCHIVED = "archived", "Archived"
        RESTORED = "restored", "Restored"
        UPDATE = "update", "Wrote an update"

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="activity")
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    actor = models.ForeignKey(
        RealmMembership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # An automation's id and name when it made the change (automations sit above this app).
    automation_id = models.PositiveIntegerField(null=True, blank=True)
    automation_name = models.CharField(max_length=120, blank=True)
    column_key = models.CharField(max_length=40, blank=True)
    column_title = models.CharField(max_length=80, blank=True)
    old = models.JSONField(null=True, blank=True)
    new = models.JSONField(null=True, blank=True)
    old_text = models.CharField(max_length=300, blank=True)
    new_text = models.CharField(max_length=300, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    objects = ActivityQuerySet.as_manager()

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["board", "-at"])]


class BoardView(TenantModel):
    """A saved way of looking at a board: table or kanban, with search, filters, sort and the
    columns it hides. Shared by everyone on the board."""

    class Kind(models.TextChoices):
        TABLE = "table", "Table"
        KANBAN = "kanban", "Kanban"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="views")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TABLE)
    config = models.JSONField(default=dict, blank=True)
    position = models.FloatField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = BoardChildQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
