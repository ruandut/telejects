"""The Demo connector: no provider, predictable answers. For development and trying the flow.

Answers depend only on the coordinates and the product, so the same site always gets the same
result. A call whose first site has certain coordinates fails (every time, so retrying it
fails too), so error handling can be seen. Each call waits a moment, so progress is visible.
"""

import hashlib
import time

from ..canonical import (
    Answer,
    CallRecord,
    CheckOutcome,
    ConnectorError,
    ErrorKind,
    ProductInfo,
    ProductRef,
    ProductType,
    SiteQuery,
    Status,
)

PRODUCTS = [
    ProductInfo("demo-fibre-100", "Demo Fibre 100", ProductType.FIBRE),
    ProductInfo("demo-fibre-1000", "Demo Fibre 1000", ProductType.FIBRE),
    ProductInfo("demo-lte", "Demo LTE", ProductType.LTE),
    ProductInfo("demo-wireless", "Demo Fixed Wireless", ProductType.FIXED_WIRELESS),
]

STATUSES = [Status.AVAILABLE, Status.NEAR_NET, Status.COVERAGE_ONLY, Status.NOT_AVAILABLE]
BANDWIDTHS = {
    "demo-fibre-100": [(10, 100)],
    "demo-fibre-1000": [(100, 1000)],
    "demo-lte": [(0, 50)],
    "demo-wireless": [(10, 50)],
}

# Seconds each call waits, like a real provider would. Tests set it to 0.
DELAY_SECONDS = 0.6


def _digest(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def fails(site: SiteQuery) -> bool:
    """About one call in thirteen fails: the ones whose first site this is true for."""
    return _digest("fail", f"{site.latitude:.5f}") % 13 == 0


def status_for(site: SiteQuery, code: str) -> Status:
    return STATUSES[_digest(f"{site.latitude:.5f}", f"{site.longitude:.5f}", code) % 4]


class DemoConnector:
    def __init__(self, spec, settings: dict, secrets: dict):
        self.spec = spec
        self.settings = settings

    def list_products(self):
        return list(PRODUCTS), [CallRecord(request={"demo": "products"})]

    def check(self, sites: list[SiteQuery], products: list[ProductRef]) -> CheckOutcome:
        if DELAY_SECONDS:
            time.sleep(DELAY_SECONDS)
        if sites and fails(sites[0]):
            raise ConnectorError(ErrorKind.PROVIDER_DOWN, "(Demo: this call fails on purpose.)")
        answers = [
            Answer(
                site_ref=site.ref,
                product_code=product.code,
                status=status_for(site, product.code),
                bandwidths=BANDWIDTHS.get(product.code, []),
            )
            for site in sites
            for product in products
        ]
        record = CallRecord(
            request={"demo": "check", "sites": [s.ref for s in sites]},
            response={"answers": len(answers)},
            status_code=200,
        )
        return CheckOutcome(answers=answers, calls=[record])

    def test_connection(self) -> None:
        return None
