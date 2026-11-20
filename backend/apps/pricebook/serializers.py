"""Request bodies of Rapid's endpoints, validated as Rapid did (api/serializers.py)."""

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import CatalogueProduct, ConnectProduct


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
