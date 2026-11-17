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
    PlatformAccountQuerySet,
    PlatformGrantQuerySet,
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


class Health(models.TextChoices):
    UNKNOWN = "unknown", "Not checked yet"
    OK = "ok", "Connected"
    FAILING = "failing", "Failing"


class Credentials(models.Model):
    """A provider account's fields: the non-secret settings, and the secrets, encrypted."""

    connector_key = models.SlugField(max_length=50)
    settings = models.JSONField(default=dict, blank=True)  # the non-secret fields
    secrets_encrypted = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    health = models.CharField(max_length=10, choices=Health.choices, default=Health.UNKNOWN)
    health_error = models.CharField(max_length=500, blank=True)
    health_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

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


class PlatformAccount(Credentials):
    """Telejects' own account with a provider, kept by platform staff (0004). Companies granted
    it connect through it, and never see its settings or secrets."""

    Health = Health

    name = models.CharField(max_length=100, unique=True)

    objects = PlatformAccountQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class PlatformGrant(TenantModel):
    """Staff let this company use a platform account. Only staff create or withdraw it."""

    account = models.ForeignKey(PlatformAccount, on_delete=models.CASCADE, related_name="grants")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PlatformGrantQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "account"], name="one_grant_per_account")
        ]

    def __str__(self):
        return f"{self.account} for {self.realm}"


class Connection(Credentials, TenantModel):
    """A company's connection to a provider: with its own account, or (when staff granted it)
    through one of Telejects' platform accounts."""

    Health = Health

    class Source(models.TextChoices):
        OWN = "own", "Your account"
        PLATFORM = "platform", "Telejects account"

    name = models.CharField(max_length=100)
    credentials = models.CharField(max_length=10, choices=Source.choices, default=Source.OWN)
    # Set when `credentials` is platform. RESTRICT: an account in use is turned off, not deleted.
    platform_account = models.ForeignKey(
        PlatformAccount, null=True, blank=True, on_delete=models.RESTRICT, related_name="+"
    )

    objects = ConnectionQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "name"], name="connection_name_in_realm"),
            models.UniqueConstraint(fields=["realm", "id"], name="connection_realm_id_pair"),
            models.CheckConstraint(
                condition=(
                    models.Q(credentials="own", platform_account__isnull=True)
                    | models.Q(credentials="platform", platform_account__isnull=False)
                ),
                name="connection_platform_account_matches_credentials",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def uses_platform(self) -> bool:
        return self.credentials == self.Source.PLATFORM

    @property
    def limit_key(self) -> str:
        """Whose limits a call counts against: the provider sees one account, so everyone on a
        platform account shares them."""
        if self.uses_platform:
            return f"platform-{self.platform_account_id}"
        return f"connection-{self.id}"


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
    # Whose credentials the call used (0004), for counting usage of platform accounts.
    credentials = models.CharField(max_length=10, blank=True)
    platform_account = models.ForeignKey(
        PlatformAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = SyncRunQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at", "-id"]
