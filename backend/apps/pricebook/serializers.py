"""Request bodies of Rapid's endpoints, validated as Rapid did (api/serializers.py)."""

from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import (
    PROVIDERS,
    VODACOM,
    AccessMedium,
    CatalogueProduct,
    ConnectProduct,
    PriceDefinition,
    SublayerProvider,
)


class SingleSiteFeasibilitySerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    products = serializers.ListField(child=serializers.IntegerField(), min_length=0, required=False)
    timeout = serializers.IntegerField(required=False, default=50, max_value=50, min_value=5)

    def validate(self, attrs):
        wanted = attrs.get("products") or []
        if wanted and CatalogueProduct.objects.filter(pk__in=wanted).count() != len(set(wanted)):
            raise ValidationError({"products": "One or more products are invalid."})
        return attrs


class SingleSiteFeasibilityQuoteSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    connect_products = serializers.ListField(
        child=serializers.IntegerField(), min_length=0, required=False
    )
    timeout = serializers.IntegerField(required=False, default=50, max_value=50, min_value=5)

    def validate(self, attrs):
        wanted = attrs.get("connect_products") or []
        if wanted:
            # A connect product of a book the company isn't offered reads as invalid too.
            offered = ConnectProduct.objects.offered_to(self.context["realm_id"])
            if offered.filter(pk__in=wanted).count() != len(set(wanted)):
                raise ValidationError(
                    {"connect_products": "One or more connect_products are invalid."}
                )
        return attrs


# --- the price book in the portal (staff only) --------------------------------------------------

ON_REQUEST = Decimal("-1")


class Cost(serializers.DecimalField):
    """Rands, or -1 for price on request (Rapid's "on request only")."""

    def __init__(self, **kwargs):
        super().__init__(max_digits=10, decimal_places=2, max_value=50000, **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value < 0 and value != ON_REQUEST:
            raise ValidationError("A cost is zero or more, or -1 for price on request.")
        return value


class PriceDefinitionInput(serializers.Serializer):
    """Rapid's ConnectProductDefinitionUpdateOrCreateSerializer, with its dialog's limits."""

    name = serializers.CharField(min_length=2, max_length=100)
    provider = serializers.ChoiceField(choices=PROVIDERS, required=False, allow_null=True)
    access_medium = serializers.PrimaryKeyRelatedField(
        queryset=AccessMedium.objects.all(), required=False, allow_null=True
    )
    product = serializers.PrimaryKeyRelatedField(
        queryset=CatalogueProduct.objects.all(), required=False, allow_null=True
    )
    sublayer = serializers.ChoiceField(
        choices=SublayerProvider.choices, required=False, allow_null=True
    )
    duration = serializers.IntegerField(min_value=1, max_value=60)
    monthly_recurring_cost = Cost()
    none_recurring_cost = Cost(required=False, default=Decimal("0.00"))
    data_allocation = serializers.IntegerField(
        min_value=0, max_value=1_000_000_000, required=False, allow_null=True
    )
    data_allocation_notes = serializers.CharField(
        max_length=255, required=False, allow_blank=True, allow_null=True
    )
    max_bandwidth = serializers.IntegerField(min_value=1, max_value=10000)
    max_upload_bandwidth = serializers.IntegerField(min_value=1, max_value=10000)
    medium = serializers.CharField(max_length=255)
    connect_products = serializers.PrimaryKeyRelatedField(
        queryset=ConnectProduct.objects.all(), many=True, required=False
    )

    def validate(self, attrs):
        """Rapid's rule: Vodacom prices an access medium, the rest a product, and the provider
        follows the product."""
        medium, product = attrs.get("access_medium"), attrs.get("product")
        provider = attrs.get("provider")
        if product is not None:
            if provider is not None and provider != product.provider:
                raise ValidationError({"provider": "Provider must match the product's provider."})
            attrs["provider"] = product.provider
        elif medium is not None:
            if provider not in (None, VODACOM):
                raise ValidationError(
                    {"provider": "Only Vodacom can use access_medium without a product."}
                )
            attrs["provider"] = VODACOM
        else:
            raise ValidationError(
                {"non_field_errors": ["Either product or access_medium must be set."]}
            )
        if medium is not None and attrs["provider"] != VODACOM:
            raise ValidationError({"access_medium": "Only Vodacom prices an access medium."})
        attrs.setdefault("data_allocation", None)
        attrs.setdefault("sublayer", None)
        self._check_unique(attrs)
        return attrs

    def _check_unique(self, attrs):
        fields = [
            "name",
            "access_medium",
            "product",
            "duration",
            "data_allocation",
            "max_bandwidth",
            "max_upload_bandwidth",
        ]
        same = PriceDefinition.objects.filter(**{f: attrs.get(f) for f in fields})
        if self.instance is not None:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise ValidationError(
                {"non_field_errors": ["The price book already has this price, with this term."]}
            )


class ConnectProductInput(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_name(self, value):
        same = ConnectProduct.objects.filter(name__iexact=value)
        if self.instance is not None:
            same = same.exclude(pk=self.instance.pk)
        if same.exists():
            raise ValidationError("A connect product with this name already exists.")
        return value
