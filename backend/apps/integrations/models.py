"""Integrations: the connector catalogue, a company's connections to providers, and the
products each connection offers.

A connector definition (spec.py) is platform data: one catalogue for every company. Everything
a company owns (its connections and their encrypted secrets, the products synced for them and
the syncs themselves) is a TenantModel.
"""

from functools import cached_property

from django.conf import settings
from django.db import models

from apps.realms.models import TenantModel

from . import crypto
from .canonical import PRODUCT_TYPE_LABELS, ProductType
from .querysets import (
    ConnectionQuerySet,
    ConnectorDefinitionQuerySet,
    ProviderProductQuerySet,
    SyncRunQuerySet,
)
from .spec import ConnectorSpec


class ConnectorDefinition(models.Model):
    """One version of a provider's definition. A saved version never changes; edits are new
    versions, and connections use the newest published one."""

    key = models.SlugField(max_length=50)
    version = models.PositiveIntegerField()
    spec = models.JSONField()
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = ConnectorDefinitionQuerySet.as_manager()

    class Meta:
        ordering = ["key", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["key", "version"], name="connector_key_version")
        ]

    def __str__(self):
        return f"{self.key} v{self.version}"

    @cached_property
    def parsed(self) -> ConnectorSpec:
        return ConnectorSpec.model_validate(self.spec)


class Connection(TenantModel):
    """A company's own account with a provider."""

    class Health(models.TextChoices):
        UNKNOWN = "unknown", "Not checked yet"
        OK = "ok", "Connected"
        FAILING = "failing", "Failing"

    name = models.CharField(max_length=100)
    connector_key = models.SlugField(max_length=50)
    settings = models.JSONField(default=dict, blank=True)  # the non-secret fields
    secrets_encrypted = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    health = models.CharField(max_length=10, choices=Health.choices, default=Health.UNKNOWN)
    health_error = models.CharField(max_length=500, blank=True)
    health_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConnectionQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "name"], name="connection_name_in_realm"),
            models.UniqueConstraint(fields=["realm", "id"], name="connection_realm_id_pair"),
        ]

    def __str__(self):
        return self.name

    @property
    def secrets(self) -> dict:
        return crypto.decrypt(self.secrets_encrypted)

    @secrets.setter
    def secrets(self, values: dict) -> None:
        self.secrets_encrypted = crypto.encrypt(values) if values else ""

    @property
    def secret_keys_set(self) -> set[str]:
        return {k for k, v in self.secrets.items() if v}

    def definition(self) -> ConnectorDefinition | None:
        return ConnectorDefinition.objects.latest_for(self.connector_key)


class ProviderProduct(TenantModel):
    """A product a connection's provider offers. Kept when the provider drops it (retired),
    because past results point at it."""

    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="products")
    code = models.CharField(max_length=200)
    name = models.CharField(max_length=255)
    product_type = models.CharField(
        max_length=20, choices=[(t.value, PRODUCT_TYPE_LABELS[t]) for t in ProductType]
    )
    raw = models.JSONField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    objects = ProviderProductQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "code"], name="product_code_per_connection"
            ),
        ]

    def __str__(self):
        return self.name


class SyncRun(TenantModel):
    """One catalogue sync or credential check of a connection."""

    class Kind(models.TextChoices):
        SYNC_PRODUCTS = "sync_products", "Product sync"
        TEST_CONNECTION = "test_connection", "Connection test"

    class Trigger(models.TextChoices):
        CONNECT = "connect", "On connecting"
        MANUAL = "manual", "By hand"
        SCHEDULED = "scheduled", "Scheduled"

    class Outcome(models.TextChoices):
        RUNNING = "running", "Running"
        OK = "ok", "Done"
        FAILED = "failed", "Failed"

    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="syncs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    trigger = models.CharField(max_length=10, choices=Trigger.choices)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, default=Outcome.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    added = models.PositiveIntegerField(default=0)
    retired = models.PositiveIntegerField(default=0)
    error_kind = models.CharField(max_length=20, blank=True)
    error = models.CharField(max_length=500, blank=True)
    definition_version = models.PositiveIntegerField(null=True, blank=True)

    objects = SyncRunQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at", "-id"]
