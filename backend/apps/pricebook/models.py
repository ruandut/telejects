"""Telejects' price book (0006): Rapid's price book, kept by staff, quoted from by companies.

Copied from Rapid's `connect` models with their ids and field names, because Rapid's clients
send and receive those ids. Everything here but the grant is platform data, like a platform
account: one book for every company it is offered to, read-only to them.
"""

from django.db import models

from apps.realms.models import TenantModel

from .querysets import (
    AccessMediumQuerySet,
    CatalogueProductQuerySet,
    ConnectProductQuerySet,
    PriceBookGrantQuerySet,
    PriceBookQuerySet,
    PriceDefinitionQuerySet,
)

# Rapid's provider numbers (connect/globals.py). They are in every response as `provider` and
# `provider_id`, so they never change; a new provider gets the next number.
VODACOM, MTN, LINK_AFRICA, HEROTEL = 0, 1, 2, 3
PROVIDERS = [
    (VODACOM, "Vodacom"),
    (MTN, "MTN"),
    (LINK_AFRICA, "LINK_AFRICA"),
    (HEROTEL, "Herotel"),
]
PROVIDER_NAMES = dict(PROVIDERS)
# Which connector definition each provider is in Telejects.
PROVIDER_CONNECTORS = {
    VODACOM: "vodacom",
    MTN: "mtn",
    LINK_AFRICA: "link_africa",
    HEROTEL: "herotel",
}


class SublayerProvider(models.IntegerChoices):
    """Whose network a definition is delivered over (Rapid's SublayerProvider)."""

    DFA = 0, "DFA"
    FROGFOOT = 1, "Frogfoot"
    LINK_AFRICA = 2, "LinkAfrica"
    METRO_FIBRE = 3, "MetroFibre"
    MTN = 4, "MTN"
    OCTOTEL = 5, "Octotel"
    OPEN_FIBRE = 6, "OpenFibre"
    OPEN_SERVE = 7, "OpenServe"
    THINKSPEED = 8, "Thinkspeed"
    VODACOM = 9, "Vodacom"
    VUMATEL = 10, "Vumatel"
    WAN = 11, "WAN"


class PriceBook(models.Model):
    """A book of prices. One, "Telejects", is made by a migration. Like a platform account it is
    offered to every company unless staff turn that off and grant it instead."""

    name = models.CharField(max_length=100, unique=True)
    available_to_all = models.BooleanField(
        default=True,
        help_text="Every company may quote from this book. Off: only companies with a grant.",
    )

    objects = PriceBookQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class PriceBookGrant(TenantModel):
    """Staff let this company quote from a book that isn't offered to all."""

    book = models.ForeignKey(PriceBook, on_delete=models.CASCADE, related_name="grants")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PriceBookGrantQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["realm", "book"], name="one_grant_per_book")]

    def __str__(self):
        return f"{self.book} for {self.realm}"


class CatalogueProduct(models.Model):
    """A provider product as Rapid numbered it (Rapid's `Product`), and which product it is in
    Telejects: a connector and the product code its catalogue sync gives."""

    product_id = models.IntegerField(
        null=True, blank=True, help_text="Rapid's provider product number, e.g. Vodacom's 10."
    )
    name = models.CharField(max_length=255)
    provider = models.IntegerField(choices=PROVIDERS)
    product_code = models.CharField(
        max_length=200,
        help_text="The product's code in Telejects: Vodacom's product id, MTN's product name.",
    )

    objects = CatalogueProductQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "product_code"], name="catalogue_product_code_per_provider"
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.provider_name}"

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAMES[self.provider]

    @property
    def connector_key(self) -> str:
        return PROVIDER_CONNECTORS[self.provider]


class AccessMedium(models.Model):
    """A Vodacom delivery method (Rapid's `AccessMedium`). Vodacom prices per access medium."""

    provider_access_medium_identifier_id = models.IntegerField(
        help_text="Vodacom's accessMediumId."
    )
    name = models.CharField(max_length=255)

    objects = AccessMediumQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "access media"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider_access_medium_identifier_id", "name"],
                name="access_medium_identifier_name",
            ),
        ]

    def __str__(self):
        return self.name if self.name != "Unknown" else "AccessMedium"


class PriceDefinition(models.Model):
    """One price (Rapid's `ConnectProductDefinition`): a speed, a term and its costs, for an
    access medium (Vodacom) or a provider product (the rest). -1 means price on request."""

    name = models.CharField(max_length=255)
    access_medium = models.ForeignKey(
        AccessMedium, null=True, blank=True, on_delete=models.CASCADE, related_name="definitions"
    )
    product = models.ForeignKey(
        CatalogueProduct,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="definitions",
    )
    provider = models.IntegerField(choices=PROVIDERS, default=VODACOM)
    sublayer = models.IntegerField(choices=SublayerProvider.choices, null=True, blank=True)
    duration = models.IntegerField(default=12, help_text="Term in months")
    monthly_recurring_cost = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="-1 means price on request"
    )
    none_recurring_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Once-off cost, such as installation. -1 means price on request",
    )
    data_allocation = models.IntegerField(default=0, null=True, blank=True, help_text="GB")
    # Null, not blank, where Rapid's answers say null: its clients see the same (also `medium`).
    data_allocation_notes = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001
    max_bandwidth = models.IntegerField(default=0, null=True, blank=True, help_text="Mbps")
    max_upload_bandwidth = models.IntegerField(default=0, null=True, blank=True, help_text="Mbps")
    medium = models.CharField(max_length=255, null=True, blank=True)  # noqa: DJ001

    objects = PriceDefinitionQuerySet.as_manager()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "name",
                    "access_medium",
                    "product",
                    "duration",
                    "data_allocation",
                    "max_bandwidth",
                    "max_upload_bandwidth",
                ],
                name="price_definition_unique",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(access_medium__isnull=False) | models.Q(product__isnull=False),
                name="price_definition_has_medium_or_product",
            ),
        ]

    def __str__(self):
        product = self.product.name if self.product else ""
        return (
            f"{self.name} - {product} {PROVIDER_NAMES[self.provider]} - DL {self.max_bandwidth}"
            f"mbps / UP {self.max_upload_bandwidth}mbps - {self.duration} months"
            f" @ R{self.monthly_recurring_cost}"
        )

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAMES[self.provider]


class ConnectProduct(models.Model):
    """What a client quotes for (Rapid's `ConnectProduct`): a named set of price definitions."""

    book = models.ForeignKey(PriceBook, on_delete=models.CASCADE, related_name="connect_products")
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)  # noqa: DJ001 (Rapid answers null)
    product_definitions = models.ManyToManyField(
        PriceDefinition, blank=True, related_name="connect_products"
    )

    objects = ConnectProductQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name
