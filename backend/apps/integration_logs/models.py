"""The integration request log (0005): every request to a provider and its answer."""

from django.db import models

from apps.realms.models import TenantModel

from .querysets import IntegrationLogQuerySet, LogRetentionQuerySet


class IntegrationLog(TenantModel):
    """One HTTP exchange with a provider (or a Python connector's call), secrets redacted.

    Rows of other apps are referred to by id (this app sits below them); they are only ever
    looked up inside the same company.
    """

    class Operation(models.TextChoices):
        CHECK_FEASIBILITY = "check_feasibility", "Feasibility check"
        SYNC_PRODUCTS = "sync_products", "Product sync"
        TEST_CONNECTION = "test_connection", "Connection test"

    created_at = models.DateTimeField(auto_now_add=True)
    operation = models.CharField(max_length=20, choices=Operation.choices)
    connection_id = models.BigIntegerField(null=True, blank=True)
    connection_name = models.CharField(max_length=100, blank=True)
    connector_key = models.CharField(max_length=50, blank=True)
    definition_version = models.PositiveIntegerField(null=True, blank=True)
    credentials = models.CharField(max_length=10, blank=True)  # own or platform
    # What it belongs to: a feasibility run and its provider check, or a sync.
    run_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    check_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    sync_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    method = models.CharField(max_length=10, blank=True)
    url = models.TextField(blank=True)
    request_headers = models.JSONField(default=dict, blank=True)
    request_body = models.TextField(blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    outcome = models.CharField(max_length=20, default="ok")  # ok, or an error kind
    error = models.CharField(max_length=500, blank=True)

    objects = IntegrationLogQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["realm", "-id"])]

    def __str__(self):
        return f"{self.method} {self.url} ({self.status_code or self.outcome})"


class LogRetention(TenantModel):
    """How many requests a company keeps. Set by platform staff in Django admin; without a row,
    the app's default (INTEGRATION_LOGS_DEFAULT_LIMIT) applies."""

    max_entries = models.PositiveIntegerField()

    objects = LogRetentionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["realm"], name="one_log_retention_per_realm")
        ]

    def __str__(self):
        return f"Keep {self.max_entries} for {self.realm}"
