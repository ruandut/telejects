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
    def __init__(self, spec, settings: dict, secrets: dict, recorder=None):
        self.spec = spec
        self.settings = settings
        self.recorder = recorder or (lambda record: None)

    def _request(self, kind: str, **body) -> dict:
        return {"method": "DEMO", "url": f"demo://{kind}", "headers": {}, "body": body}

    def list_products(self):
        record = CallRecord(
            request=self._request("products"),
            status_code=200,
            response=[{"code": p.code, "name": p.name} for p in PRODUCTS],
            duration_ms=0,
        )
        self.recorder(record)
        return list(PRODUCTS), [record]

    def check(self, sites: list[SiteQuery], products: list[ProductRef]) -> CheckOutcome:
        started = time.monotonic()
        if DELAY_SECONDS:
            time.sleep(DELAY_SECONDS)
        request = self._request(
            "feasibility",
            sites=[s.as_context() for s in sites],
            products=[p.code for p in products],
        )
        if sites and fails(sites[0]):
            error = ConnectorError(ErrorKind.PROVIDER_DOWN, "(Demo: this call fails on purpose.)")
            self.recorder(
                CallRecord(
                    request=request,
                    status_code=503,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_kind=error.kind,
                    error=error.message,
                )
            )
            raise error
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
            request=request,
            response={
                "answers": [
                    {"site": a.site_ref, "product": a.product_code, "status": a.status}
                    for a in answers
                ]
            },
            status_code=200,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        self.recorder(record)
        return CheckOutcome(answers=answers, calls=[record])

    def test_connection(self) -> None:
        self.list_products()
