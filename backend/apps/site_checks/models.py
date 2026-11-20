"""One-site feasibility checks (0006): one place, checked now, with the caller waiting.

A check asks each provider once, through the company's own connection to it (own account or one
of Telejects'), as a bulk run does. Its results are the canonical answers, kept so the API can
return stable ids and the Logs section can show what was sent.
"""

from django.conf import settings
from django.db import models

from apps.integrations.canonical import PRODUCT_TYPE_LABELS, STATUS_LABELS, ProductType, Status
from apps.integrations.models import Connection, ProviderProduct
from apps.realms.models import TenantModel

from .querysets import SiteCheckCallQuerySet, SiteCheckQuerySet, SiteCheckResultQuerySet


class SiteCheck(TenantModel):
    """Someone (a member, or an API client) asked what is feasible at one place."""

    created_at = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    timeout_seconds = models.PositiveSmallIntegerField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The API client that asked, by id (api_clients sits beside this app, not below it).
    api_client_id = models.BigIntegerField(null=True, blank=True)

    objects = SiteCheckQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.latitude}, {self.longitude}"


class SiteCheckCall(TenantModel):
    """One provider asked about the place, through one of the company's connections."""

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    site_check = models.ForeignKey(SiteCheck, on_delete=models.CASCADE, related_name="calls")
    connection = models.ForeignKey(
        Connection, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    connector_key = models.SlugField(max_length=50)
    products = models.ManyToManyField(ProviderProduct, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error_kind = models.CharField(max_length=20, blank=True)
    error = models.CharField(max_length=500, blank=True)
    credentials = models.CharField(max_length=10, blank=True)
    platform_account_id = models.BigIntegerField(null=True, blank=True)
    definition_version = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = SiteCheckCallQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.connector_key} for {self.site_check_id}"

    @property
    def is_open(self) -> bool:
        return self.status in (self.Status.PENDING, self.Status.RUNNING)


class SiteCheckResult(TenantModel):
    """What a provider said it can deliver there: one product (and variant). Products it can't
    deliver get no row, as in bulk runs."""

    site_check = models.ForeignKey(SiteCheck, on_delete=models.CASCADE, related_name="results")
    call = models.ForeignKey(SiteCheckCall, on_delete=models.CASCADE, related_name="results")
    product = models.ForeignKey(ProviderProduct, on_delete=models.RESTRICT, related_name="+")
    connector_key = models.SlugField(max_length=50)
    product_code = models.CharField(max_length=200)
    variant_code = models.CharField(max_length=100, blank=True)
    variant_name = models.CharField(max_length=255, blank=True)
    product_type = models.CharField(
        max_length=20, choices=[(t.value, PRODUCT_TYPE_LABELS[t]) for t in ProductType]
    )
    status = models.CharField(max_length=20, choices=[(s.value, STATUS_LABELS[s]) for s in Status])
    bandwidths = models.JSONField(default=list, blank=True)  # [[low, high], ...] in Mbps
    note = models.CharField(max_length=255, blank=True)

    objects = SiteCheckResultQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.product_code} {self.variant_name}".strip()

    @property
    def upper_bandwidths(self) -> list[int]:
        """The top of each bandwidth range offered (Rapid prices against these)."""
        tops = []
        for low, high in self.bandwidths or []:
            top = high if high is not None else low
            if top is not None and top not in tops:
                tops.append(int(top))
        return tops
