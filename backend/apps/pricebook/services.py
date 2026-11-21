"""Rapid's single-site feasibility and quote, on Telejects' checks and price book (0006).

The responses are Rapid's, field for field (api/views/connect/feasibility_views.py and
api/serializers.py in connect-rapid), so its clients keep working. Where Rapid's behaviour is
odd it is kept on purpose, and said so below.
"""

from dataclasses import dataclass, field

from django.db import transaction

from apps.integrations.canonical import ErrorKind
from apps.site_checks import services as site_checks
from apps.site_checks.models import SiteCheck, SiteCheckCall, SiteCheckResult

from .models import (
    MTN,
    PROVIDER_CONNECTORS,
    PROVIDER_NAMES,
    VODACOM,
    AccessMedium,
    CatalogueProduct,
    ConnectProduct,
    PriceDefinition,
)

NOTICE = "None of the prices in this API are final. Please contact us for a formal quote."
CONNECTOR_PROVIDERS = {key: number for number, key in PROVIDER_CONNECTORS.items()}

EXCEPTION_NAMES = {
    ErrorKind.AUTH: "Auth",
    ErrorKind.RATE_LIMITED: "RateLimited",
    ErrorKind.TIMEOUT: "Timeout",
    ErrorKind.PROVIDER_DOWN: "ProviderDown",
    ErrorKind.BAD_REQUEST: "BadRequest",
    ErrorKind.BAD_RESPONSE: "BadResponse",
}


# --- Rapid's shapes ---------------------------------------------------------------------------


def money(value) -> str:
    """Rapid's DRF DecimalField: two places, as a string. -1 is "-1.00" (price on request)."""
    return f"{value:.2f}"


def product_data(product: CatalogueProduct | None) -> dict | None:
    """Rapid's ConciseProductSerializer."""
    if product is None:
        return None
    return {"id": product.id, "name": product.name, "provider_name": product.provider_name}


def access_medium_data(medium: AccessMedium, product: CatalogueProduct | None = None) -> dict:
    """Rapid's ConciseAccessMediumSerializer (its `product` comes from context, else null)."""
    return {
        "id": medium.id,
        "name": medium.name,
        "provider_access_medium_identifier_id": medium.provider_access_medium_identifier_id,
        "product": product_data(product),
    }


def catalogue_product_data(product: CatalogueProduct) -> dict:
    """Rapid's ProductSerializer (`/api/product/`)."""
    return {
        "id": product.id,
        "provider_verbose": {"id": product.provider, "name": product.provider_name},
        "name": product.name,
        "provider": product.provider,
    }


def connect_product_data(connect_product: ConnectProduct) -> dict:
    """Rapid's ConnectProductSerializer (`/api/connect-product/`): its definitions' provider
    products, each once, in definition order."""
    seen, products = set(), []
    for definition in connect_product.product_definitions.all():
        if definition.product_id and definition.product_id not in seen:
            seen.add(definition.product_id)
            products.append(product_data(definition.product))
    return {
        "name": connect_product.name,
        "id": connect_product.id,
        "description": connect_product.description,
        "products": products,
    }


def price_option_data(definition: PriceDefinition) -> dict:
    """Rapid's compile_common_price_option over ConnectProductDefinitionQuoteSerializer."""
    return {
        "id": definition.id,
        "duration": definition.duration,
        "monthly_recurring_cost": money(definition.monthly_recurring_cost),
        "none_recurring_cost": money(definition.none_recurring_cost),
        "data_allocation": definition.data_allocation,
        "data_allocation_notes": definition.data_allocation_notes,
        "max_bandwidth": definition.max_bandwidth,
        "max_upload_bandwidth": definition.max_upload_bandwidth,
        "medium": definition.medium,
        "product": product_data(definition.product),
        "access_medium": (
            access_medium_data(definition.access_medium) if definition.access_medium else None
        ),
    }


# --- what was found at the place, as Rapid's "available connections" --------------------------


@dataclass
class Available:
    """One of Rapid's AvailableConnections: a feasible Vodacom access medium, or a feasible
    product of another provider, with the top of each bandwidth range offered."""

    id: int  # the first one-site result it came from
    product: CatalogueProduct
    access_medium: AccessMedium | None = None
    bandwidths: list[int] = field(default_factory=list)


def _access_medium_for(result: SiteCheckResult) -> AccessMedium | None:
    """Vodacom's access medium, made the first time it is seen, as Rapid did."""
    try:
        identifier = int(result.variant_code)
    except TypeError, ValueError:
        return None
    medium = AccessMedium.objects.filter(
        provider_access_medium_identifier_id=identifier, name=result.variant_name
    ).first()
    if medium is None:
        with transaction.atomic():
            medium, _ = AccessMedium.objects.get_or_create(
                provider_access_medium_identifier_id=identifier, name=result.variant_name
            )
    return medium


def available_at(check: SiteCheck, products: list[CatalogueProduct]) -> list[Available]:
    """The check's feasible results for these products, one per Vodacom access medium and one
    per other product, oldest first (Rapid kept one row per place and medium or product)."""
    by_key = {(p.connector_key, p.product_code): p for p in products}
    found: dict[tuple, Available] = {}
    results = SiteCheckResult.objects.in_realm_id(check.realm_id).of_check(check).feasible()
    for result in results.order_by("id"):
        product = by_key.get((result.connector_key, result.product_code))
        if product is None:
            continue
        medium = None
        if product.provider == VODACOM:
            medium = _access_medium_for(result)
            if medium is None:
                continue
            key = ("medium", medium.id)
        else:
            key = ("product", product.id)
        row = found.get(key)
        if row is None:
            row = found[key] = Available(id=result.id, product=product, access_medium=medium)
        for top in result.upper_bandwidths:
            if top not in row.bandwidths:
                row.bandwidths.append(top)
    return list(found.values())


# --- running the check ----------------------------------------------------------------------


def _wanted(products: list[CatalogueProduct]) -> dict[str, list[str]]:
    wanted: dict[str, list[str]] = {}
    for product in products:
        codes = wanted.setdefault(product.connector_key, [])
        if product.product_code not in codes:
            codes.append(product.product_code)
    return wanted


def _exceptions(calls: list[SiteCheckCall], skipped, timeout: int) -> list[dict]:
    """Rapid's `exceptions`: one per provider that failed, didn't answer in time, or wasn't
    asked because the company isn't connected to it."""
    found = []
    for item in skipped:
        found.append({"exception": item.kind, "message": item.message})
    for call in calls:
        if call.is_open:
            found.append(
                {
                    "exception": "Timeout",
                    "message": f"{call.connector_key} didn't answer within {timeout} seconds.",
                }
            )
        elif call.status == SiteCheckCall.Status.FAILED:
            name = EXCEPTION_NAMES.get(call.error_kind, "ConnectorError")
            found.append({"exception": name, "message": f"{call.connector_key}: {call.error}"})
    return found


def check_place(realm_id, *, latitude, longitude, products, timeout, user=None, client_id=None):
    """Ask every provider of `products` about the place, and wait for the answers.
    Returns (check, exceptions)."""
    check, skipped = site_checks.start_check(
        realm_id,
        latitude=latitude,
        longitude=longitude,
        wanted=_wanted(products),
        timeout=timeout,
        user=user,
        api_client_id=client_id,
    )
    calls = site_checks.wait_for(check, timeout)
    return check, _exceptions(calls, skipped, timeout)


def connected_products(realm_id: int) -> list[CatalogueProduct]:
    """Every catalogue product of a provider the company is connected to: what Rapid's
    single-site check asks about when no products are named."""
    keys = {
        key
        for key in PROVIDER_CONNECTORS.values()
        if site_checks.connection_for(realm_id, key) is not None
    }
    providers = [CONNECTOR_PROVIDERS[key] for key in keys]
    return list(CatalogueProduct.objects.filter(provider__in=providers).order_by("id"))


def single_site(realm_id, *, latitude, longitude, products, timeout, user=None, client_id=None):
    """Rapid's `single-site-feasibility`: what is feasible at the place."""
    check, exceptions = check_place(
        realm_id,
        latitude=latitude,
        longitude=longitude,
        products=products,
        timeout=timeout,
        user=user,
        client_id=client_id,
    )
    data = []
    for row in available_at(check, products):
        if row.access_medium is not None:
            medium = access_medium_data(row.access_medium, row.product)
        else:
            medium = {"product": product_data(row.product)}
        data.append({"id": row.id, "access_medium": medium})
    return {"success": True, "exceptions": exceptions, "data": data}


# --- the quote --------------------------------------------------------------------------------


def _definitions_of(connect_product: ConnectProduct) -> list[PriceDefinition]:
    return list(
        connect_product.product_definitions.select_related("product", "access_medium").order_by(
            "id"
        )
    )


def quote_products(connect_products: list[ConnectProduct]) -> list[CatalogueProduct]:
    """The provider products a quote checks: those its definitions name (Rapid's
    extract_provider_product_ids). A Vodacom definition without a product checks nothing."""
    seen, found = set(), []
    for connect_product in connect_products:
        for definition in _definitions_of(connect_product):
            if definition.product_id and definition.product_id not in seen:
                seen.add(definition.product_id)
                found.append(definition.product)
    return found


def _price_book_for(connect_product: ConnectProduct, rows: list[Available]) -> list[dict]:
    """Rapid's per-product price list: the definitions for each connection found, at a
    bandwidth offered there, each once.

    Only Vodacom (by access medium) and MTN (by product) are priced, as in Rapid
    (extract_product_access_medium_ids): Link Africa and Herotel never are (Ruan, 2026-11-17)."""
    definitions = _definitions_of(connect_product)
    mediums = {
        d.access_medium_id for d in definitions if d.provider == VODACOM and d.access_medium_id
    }
    products = {d.product_id for d in definitions if d.provider == MTN and d.product_id}
    seen, listed = set(), []
    for row in rows:
        if row.access_medium is not None:
            if row.access_medium.id not in mediums:
                continue
            matches = [d for d in definitions if d.access_medium_id == row.access_medium.id]
        else:
            if row.product.id not in products:
                continue
            matches = [d for d in definitions if d.product_id == row.product.id]
        for definition in matches:
            if definition.max_bandwidth in row.bandwidths and definition.id not in seen:
                seen.add(definition.id)
                listed.append(definition)
    return listed


def _grouped(definitions: list[PriceDefinition]) -> list[dict]:
    """Rapid's grouping: Vodacom's by access medium and name, first; then others by product."""
    by_medium: dict[str, dict] = {}
    by_product: dict[int, dict] = {}
    for definition in definitions:
        if definition.access_medium is None:
            groups, key = by_product, definition.product_id
        else:
            groups, key = by_medium, f"{definition.access_medium_id}{definition.name}"
        if key not in groups:
            groups[key] = {
                "name": definition.name,
                "provider": PROVIDER_NAMES[definition.provider],
                # Rapid reads the product's provider: null on a definition without a product.
                "provider_id": definition.product.provider if definition.product else None,
                "price_options": [],
            }
        groups[key]["price_options"].append(price_option_data(definition))
    return list(by_medium.values()) + list(by_product.values())


def quote(realm_id, *, latitude, longitude, connect_products, timeout, user=None, client_id=None):
    """Rapid's `single-site-feasibility-quote`: prices for what is feasible at the place."""
    products = quote_products(connect_products)
    check, exceptions = check_place(
        realm_id,
        latitude=latitude,
        longitude=longitude,
        products=products,
        timeout=timeout,
        user=user,
        client_id=client_id,
    )
    rows = available_at(check, products)
    data = []
    for connect_product in connect_products:
        grouped = _grouped(_price_book_for(connect_product, rows))
        if grouped:
            data.append(
                {
                    "connect_product_name": connect_product.name,
                    "connect_product_id": connect_product.id,
                    "products": grouped,
                }
            )
    return {"success": True, "exceptions": exceptions, "notice": NOTICE, "data": data}


# --- the price book in the portal: Rapid's price book admin page --------------------------------

# Rapid's connection mediums (ConnectionMediumSelect).
MEDIUMS = ["Fibre", "Wireless", "LTE", "5G", "Wireless and Fibre"]


def definition_data(definition: PriceDefinition, connect_products=None) -> dict:
    """Rapid's ConnectProductDefinitionSerializer (`/api/connect-product-definition/`), with
    `connect_products` limited to the ones given (those the reader may see)."""
    if connect_products is None:
        connect_products = definition.connect_products.all()
    return {
        "id": definition.id,
        "access_medium": (
            access_medium_data(definition.access_medium) if definition.access_medium else None
        ),
        "product": product_data(definition.product),
        "connect_products": [
            {"id": c.id, "name": c.name} for c in sorted(connect_products, key=lambda c: c.id)
        ],
        "name": definition.name,
        "provider": definition.provider,
        "sublayer": definition.sublayer,
        "duration": definition.duration,
        "monthly_recurring_cost": money(definition.monthly_recurring_cost),
        "none_recurring_cost": money(definition.none_recurring_cost),
        "data_allocation": definition.data_allocation,
        "data_allocation_notes": definition.data_allocation_notes,
        "max_bandwidth": definition.max_bandwidth,
        "max_upload_bandwidth": definition.max_upload_bandwidth,
        "medium": definition.medium,
    }


def options_data() -> dict:
    """What the price book's filters and forms choose from."""
    from .models import PROVIDERS, SublayerProvider

    used = PriceDefinition.objects.exclude(medium__isnull=True).exclude(medium="")
    mediums = list(dict.fromkeys([*MEDIUMS, *used.values_list("medium", flat=True).distinct()]))
    return {
        "providers": [{"value": number, "label": name} for number, name in PROVIDERS],
        "sublayers": [{"value": c.value, "label": c.label} for c in SublayerProvider],
        "mediums": mediums,
        "access_media": [
            {"id": m.id, "name": m.name, "identifier": m.provider_access_medium_identifier_id}
            for m in AccessMedium.objects.order_by("name", "id")
        ],
        "products": [
            {"id": p.id, "name": p.name, "provider": p.provider}
            for p in CatalogueProduct.objects.order_by("name", "id")
        ],
    }


@transaction.atomic
def save_definition(
    definition: PriceDefinition | None, values: dict, connect_products: list | None
) -> PriceDefinition:
    """Create or change a definition, as Rapid's price book admin did. With `connect_products`
    given, the definition belongs to exactly those afterwards."""
    definition = definition or PriceDefinition()
    for name, value in values.items():
        setattr(definition, name, value)
    definition.save()
    if connect_products is not None:
        definition.connect_products.set(connect_products)
    return definition


def delete_definition(definition: PriceDefinition) -> None:
    definition.delete()


def save_connect_product(connect_product: ConnectProduct | None, values: dict) -> ConnectProduct:
    from . import books

    connect_product = connect_product or ConnectProduct(book=books.default_book())
    for name, value in values.items():
        setattr(connect_product, name, value)
    connect_product.save()
    return connect_product


def delete_connect_product(connect_product: ConnectProduct) -> None:
    """Its definitions stay, as in Rapid: they may belong to other connect products."""
    connect_product.delete()
