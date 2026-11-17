"""Feasibility runs: a list of sites checked against the products a company picked.

A run has its sites (the uploaded rows), the provider checks that answer them (one per provider
call: a batch of coordinates x one connection) and the results those checks wrote. Results are
written as each check finishes and never change afterwards.
"""

from django.conf import settings
from django.db import models

from apps.integrations.canonical import PRODUCT_TYPE_LABELS, STATUS_LABELS, ProductType, Status
from apps.integrations.models import Connection, PlatformAccount, ProviderProduct
from apps.realms.models import TenantModel

from .querysets import (
    FeasibilityResultQuerySet,
    FeasibilityRunQuerySet,
    ProviderCheckQuerySet,
    RunSiteQuerySet,
)


class FeasibilityRun(TenantModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    products = models.ManyToManyField(ProviderProduct, related_name="feasibility_runs")
    # The uploaded file's column names in order, and which ones hold the name and coordinates.
    columns = models.JSONField(default=list)
    mapping = models.JSONField(default=dict)
    site_count = models.PositiveIntegerField(default=0)
    checks_total = models.PositiveIntegerField(default=0)
    checks_done = models.PositiveIntegerField(default=0)
    checks_failed = models.PositiveIntegerField(default=0)
    checks_cancelled = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = FeasibilityRunQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "id"], name="feasibility_run_realm_id_pair")
        ]

    def __str__(self):
        return self.name

    @property
    def is_going(self) -> bool:
        return self.status in (self.Status.QUEUED, self.Status.RUNNING)


class RunSite(TenantModel):
    """One uploaded row."""

    run = models.ForeignKey(FeasibilityRun, on_delete=models.CASCADE, related_name="sites")
    line_number = models.PositiveIntegerField()
    name = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    # The whole uploaded row (column name -> text), for the export.
    row = models.JSONField(default=dict)

    objects = RunSiteQuerySet.as_manager()

    class Meta:
        ordering = ["line_number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["run", "line_number"], name="site_line_per_run")
        ]

    def __str__(self):
        return f"{self.line_number}: {self.name}"

    @property
    def coordinates(self) -> tuple:
        return (self.latitude, self.longitude)


class ProviderCheck(TenantModel):
    """One provider call's worth of work: some coordinates against one connection."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    run = models.ForeignKey(FeasibilityRun, on_delete=models.CASCADE, related_name="checks")
    # RESTRICT: a connection with past calls is disabled, never deleted on its own
    # (integrations.services); deleting the whole company still takes both.
    connection = models.ForeignKey(Connection, on_delete=models.RESTRICT, related_name="+")
    # Every site at the coordinates this call asks about; sites sharing them share the answer.
    sites = models.ManyToManyField(RunSite, related_name="checks")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error_kind = models.CharField(max_length=20, blank=True)
    error = models.CharField(max_length=500, blank=True)
    definition_version = models.PositiveIntegerField(null=True, blank=True)
    # Whose credentials the call used (0004): "own" or "platform", and which platform account.
    credentials = models.CharField(max_length=10, blank=True)
    platform_account = models.ForeignKey(
        PlatformAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    # What was sent and received, secrets redacted.
    calls = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = ProviderCheckQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.PENDING, self.Status.RUNNING)


class FeasibilityResult(TenantModel):
    """What a provider said about one product (and variant) at one site."""

    run = models.ForeignKey(FeasibilityRun, on_delete=models.CASCADE, related_name="results")
    site = models.ForeignKey(RunSite, on_delete=models.CASCADE, related_name="results")
    check_run = models.ForeignKey(ProviderCheck, on_delete=models.CASCADE, related_name="results")
    # RESTRICT: results keep their product readable, so a product is retired, never deleted on
    # its own; deleting the whole company still takes both.
    product = models.ForeignKey(ProviderProduct, on_delete=models.RESTRICT, related_name="+")
    variant_code = models.CharField(max_length=100, blank=True)
    variant_name = models.CharField(max_length=255, blank=True)
    product_type = models.CharField(
        max_length=20, choices=[(t.value, PRODUCT_TYPE_LABELS[t]) for t in ProductType]
    )
    status = models.CharField(max_length=20, choices=[(s.value, STATUS_LABELS[s]) for s in Status])
    bandwidths = models.JSONField(default=list, blank=True)  # [[low, high], ...] in Mbps
    note = models.CharField(max_length=255, blank=True)

    objects = FeasibilityResultQuerySet.as_manager()

    class Meta:
        ordering = ["site_id", "product_id", "variant_name", "id"]
