"""How the public API docs describe Rapid's endpoints (0006).

The views build Rapid's responses by hand (services.py), so these serializers only describe them;
nothing is serialized through them. `test_api_docs.py` holds the description to the contract
responses in `rapid_responses/`, which are also the examples shown.
"""

import json
from functools import cache
from pathlib import Path

from drf_spectacular.utils import OpenApiExample, OpenApiParameter
from rest_framework import serializers

RESPONSES = Path(__file__).resolve().parent / "rapid_responses"


@cache
def rapid_response(name: str):
    """A contract response, with a made-up id where Rapid's ids can't be ours."""
    body = json.loads((RESPONSES / f"{name}.json").read_text())
    for number, row in enumerate(body.get("data", []), start=9001):
        if row.get("id") == "<result>":
            row["id"] = number
    return body


def example(name: str) -> list[OpenApiExample]:
    return [OpenApiExample("Example", value=rapid_response(name), response_only=True)]


def page_example(name: str) -> list[OpenApiExample]:
    """A list's example: one of its results, which the docs set in a page of results."""
    value = rapid_response(name)["results"][-1]
    return [OpenApiExample("Example", value=value, response_only=True)]


PLACE = {"latitude": -26.1076, "longitude": 28.0567}


# --- shared pieces ---------------------------------------------------------------------------


class ConciseProduct(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    provider_name = serializers.CharField(help_text="`Vodacom`, `MTN`, `LINK_AFRICA`, `Herotel`.")


class AccessMedium(serializers.Serializer):
    """A Vodacom access medium. Other providers' results have only `product`."""

    id = serializers.IntegerField(required=False)
    name = serializers.CharField(required=False)
    provider_access_medium_identifier_id = serializers.IntegerField(required=False)
    product = ConciseProduct(allow_null=True)


class ProviderException(serializers.Serializer):
    exception = serializers.CharField(
        help_text="Why a provider gave no answer: `Timeout`, `Auth`, `NotConnected`, ..."
    )
    message = serializers.CharField()


class FailedCheck(serializers.Serializer):
    error = serializers.CharField(help_text='"Failed to conduct feasibility: ..."')


class Detail(serializers.Serializer):
    detail = serializers.CharField()


ERRORS = {401: Detail, 403: Detail}


# --- single-site feasibility -----------------------------------------------------------------


class Available(serializers.Serializer):
    id = serializers.IntegerField(help_text="Telejects' id for this result, unique and stable.")
    access_medium = AccessMedium()


class SingleSiteResponse(serializers.Serializer):
    success = serializers.BooleanField()
    exceptions = ProviderException(many=True)
    data = Available(many=True)


SINGLE_SITE_REQUEST = [
    OpenApiExample(
        "Example", value={**PLACE, "products": [23, 24, 32], "timeout": 30}, request_only=True
    )
]


# --- quote -----------------------------------------------------------------------------------


class PriceOption(serializers.Serializer):
    id = serializers.IntegerField()
    duration = serializers.IntegerField(help_text="Months.")
    monthly_recurring_cost = serializers.CharField(
        help_text='Rands, two decimals. "-1.00" is price on request.'
    )
    none_recurring_cost = serializers.CharField(help_text="Once-off, as above.")
    data_allocation = serializers.IntegerField(allow_null=True)
    data_allocation_notes = serializers.CharField(allow_blank=True)
    max_bandwidth = serializers.IntegerField(help_text="Mbps down.")
    max_upload_bandwidth = serializers.IntegerField(help_text="Mbps up.")
    medium = serializers.CharField()
    product = ConciseProduct(allow_null=True)
    access_medium = AccessMedium(allow_null=True)


class QuotedProduct(serializers.Serializer):
    name = serializers.CharField()
    provider = serializers.CharField()
    provider_id = serializers.IntegerField(allow_null=True)
    price_options = PriceOption(many=True)


class QuotedConnectProduct(serializers.Serializer):
    connect_product_name = serializers.CharField()
    connect_product_id = serializers.IntegerField()
    products = QuotedProduct(many=True)


class QuoteResponse(serializers.Serializer):
    success = serializers.BooleanField()
    exceptions = ProviderException(many=True)
    notice = serializers.CharField()
    data = QuotedConnectProduct(many=True)


QUOTE_REQUEST = [
    OpenApiExample(
        "Example", value={**PLACE, "connect_products": [1, 5], "timeout": 30}, request_only=True
    )
]


# --- the price book's lists ------------------------------------------------------------------


class ConnectProductData(serializers.Serializer):
    name = serializers.CharField()
    id = serializers.IntegerField()
    description = serializers.CharField(allow_blank=True)
    products = ConciseProduct(many=True)


class ProviderVerbose(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class CatalogueProductData(serializers.Serializer):
    id = serializers.IntegerField()
    provider_verbose = ProviderVerbose()
    name = serializers.CharField()
    provider = serializers.IntegerField(help_text="0 Vodacom, 1 MTN, 2 Link Africa, 3 Herotel.")


SEARCH = OpenApiParameter("search_string", str, description="Part of the name.")
PROVIDER = OpenApiParameter(
    "provider", int, description="0 Vodacom, 1 MTN, 2 Link Africa, 3 Herotel."
)
ID = OpenApiParameter("id", int, OpenApiParameter.PATH)
