"""Insights: dashboards of chart widgets over boards' items (0007).

A dashboard belongs to a project (its boards), or to the company (every project the viewer can
see). Widgets hold their query as JSON (`query.py` says what it may contain); their data is
always worked out for the person looking, over only the items they may see.
"""

from django.conf import settings
from django.db import models

from apps.projects.models import Project
from apps.realms.models import TenantModel

from .querysets import DashboardQuerySet, WidgetQuerySet


class Dashboard(TenantModel):
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    name = models.CharField(max_length=120)
    position = models.FloatField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DashboardQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]


class Widget(TenantModel):
    class Kind(models.TextChoices):
        BAR = "bar", "Bar"
        STACKED = "stacked", "Stacked bar"
        LINE = "line", "Line"
        AREA = "area", "Area"
        PIE = "pie", "Pie"
        NUMBER = "number", "Number"
        TABLE = "table", "Table"

    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    title = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    config = models.JSONField(default=dict)
    position = models.FloatField(default=0)
    width = models.PositiveSmallIntegerField(default=1)  # of 3 columns

    objects = WidgetQuerySet.as_manager()

    class Meta:
        ordering = ["position", "id"]
