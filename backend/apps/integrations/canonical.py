"""Our side of the abstraction: what the rest of the app knows about providers.

Services, tasks, the API and the UI only ever see these shapes. A connector (a definition run by
engine.py, or a Python class in connectors/) turns a provider's API into them.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class ProductType(StrEnum):
    """The system list every provider product maps onto, so results read across providers."""

    FIBRE = "fibre"
    FIXED_WIRELESS = "fixed_wireless"
    LTE = "lte"
    FIVE_G = "5g"
    MICROWAVE = "microwave"
    SATELLITE = "satellite"
    OTHER = "other"


PRODUCT_TYPE_LABELS = {
    ProductType.FIBRE: "Fibre",
    ProductType.FIXED_WIRELESS: "Fixed wireless",
    ProductType.LTE: "LTE",
    ProductType.FIVE_G: "5G",
    ProductType.MICROWAVE: "Microwave",
    ProductType.SATELLITE: "Satellite",
    ProductType.OTHER: "Other",
}


class Status(StrEnum):
    """What a provider said about one product at one site."""

    AVAILABLE = "available"
    NEAR_NET = "near_net"  # close to the network; needs a build
    COVERAGE_ONLY = "coverage_only"  # in coverage; needs planning or a survey
    NOT_AVAILABLE = "not_available"


STATUS_LABELS = {
    Status.AVAILABLE: "Available",
    Status.NEAR_NET: "Near-net",
    Status.COVERAGE_ONLY: "Coverage only",
    Status.NOT_AVAILABLE: "Not available",
}


class ErrorKind(StrEnum):
    AUTH = "auth"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_DOWN = "provider_down"
    BAD_REQUEST = "bad_request"
    BAD_RESPONSE = "bad_response"


RETRYABLE = {ErrorKind.RATE_LIMITED, ErrorKind.TIMEOUT, ErrorKind.PROVIDER_DOWN}

ERROR_MESSAGES = {
    ErrorKind.AUTH: "The provider refused this connection's credentials.",
    ErrorKind.RATE_LIMITED: "The provider asked us to slow down.",
    ErrorKind.TIMEOUT: "The provider didn't answer in time.",
    ErrorKind.PROVIDER_DOWN: "The provider's service is unavailable.",
    ErrorKind.BAD_REQUEST: "The provider rejected the request.",
    ErrorKind.BAD_RESPONSE: "The provider's answer couldn't be read.",
}


class ConnectorError(Exception):
    """A provider call that failed. `detail` is safe to show: it never contains a secret."""

    def __init__(self, kind: ErrorKind, detail: str = ""):
        self.kind = ErrorKind(kind)
        self.detail = detail
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE

    @property
    def message(self) -> str:
        base = ERROR_MESSAGES[self.kind]
        return f"{base} {self.detail}".strip() if self.detail else base


@dataclass(frozen=True)
class SiteQuery:
    ref: str  # ours, to match answers back to sites
    name: str
    latitude: Decimal
    longitude: Decimal
    bandwidth_mbps: int | None = None
    term_months: int | None = None

    def as_context(self) -> dict:
        return {
            "ref": self.ref,
            "name": self.name,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            "bandwidth_mbps": self.bandwidth_mbps,
            "term_months": self.term_months,
        }


@dataclass(frozen=True)
class ProductRef:
    """A provider product as a request names it."""

    code: str
    name: str
    product_type: ProductType = ProductType.OTHER


@dataclass(frozen=True)
class ProductInfo:
    """A provider product as a catalogue sync finds it."""

    code: str
    name: str
    product_type: ProductType
    raw: Any = None


@dataclass(frozen=True)
class Answer:
    """One product (and variant) at one site."""

    site_ref: str
    product_code: str
    status: Status
    variant_code: str = ""
    variant_name: str = ""
    product_type: ProductType | None = None  # when the variant decides it (Vodacom's media)
    bandwidths: list[tuple[int | None, int | None]] = field(default_factory=list)
    note: str = ""


@dataclass
class CallRecord:
    """What was sent and what came back, for debugging. Secrets are redacted before this."""

    request: dict = field(default_factory=dict)
    response: Any = None
    status_code: int | None = None


@dataclass
class CheckOutcome:
    answers: list[Answer]
    calls: list[CallRecord] = field(default_factory=list)
