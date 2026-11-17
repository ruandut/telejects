"""The connector definition: a provider described as data.

Platform staff write one per provider (built-in ones live in definitions/*.json). It says what a
company fills in to connect, where the secrets go, how to build each request from our canonical
model, and how to read the provider's answers back into it (JMESPath, see engine.py). Nothing in
a definition can run code: requests are filled from a fixed context, answers are read with
JMESPath, and the Python escape hatch can only name a class under apps.integrations.connectors.
"""

from typing import Any, Literal
from urllib.parse import urlparse

import jmespath
from jmespath.exceptions import JMESPathError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import ErrorKind, ProductType, Status

PYTHON_CONNECTORS = "apps.integrations.connectors."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_expression(value: str | None) -> str | None:
    if value is not None:
        try:
            jmespath.compile(value)
        except JMESPathError as error:
            raise ValueError(f"not a valid JMESPath expression: {value!r} ({error})") from None
    return value


class ConnectionField(_Strict):
    """Something a company fills in when it connects the provider."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    help: str = ""
    type: Literal["text", "email", "secret"] = "text"
    required: bool = True

    @property
    def secret(self) -> bool:
        return self.type == "secret"


class AuthPlacement(_Strict):
    """Where one secret field goes on every request."""

    field: str
    location: Literal["header", "query", "body"]
    name: str


class RequestTemplate(_Strict):
    """A request built from the call context (see templating.py)."""

    method: Literal["GET", "POST"] = "GET"
    path: str = ""
    query: dict[str, Any] = {}
    headers: dict[str, str] = {}
    body: Any = None


class TypeRule(_Strict):
    """When `when` holds (JMESPath, truthy), the product type is `type`."""

    when: str
    type: ProductType

    _check = field_validator("when")(_check_expression)


class StatusRule(_Strict):
    when: str
    status: Status

    _check = field_validator("when")(_check_expression)


class ErrorRule(_Strict):
    """An answer that means failure even with HTTP 200 (or a status to read differently)."""

    when: str | None = None  # JMESPath on the parsed body
    http_status: int | None = None
    kind: ErrorKind
    detail: str | None = None  # JMESPath for a safe message from the body

    _check = field_validator("when", "detail")(_check_expression)


class ProductsSpec(_Strict):
    """How to get the provider's product catalogue: a request, or a fixed list."""

    request: RequestTemplate | None = None
    static: list[dict[str, Any]] | None = None
    items: str = "@"  # JMESPath: the list of products in the answer
    code: str  # JMESPath on one product
    name: str
    type_rules: list[TypeRule] = []
    default_type: ProductType = ProductType.OTHER
    timeout_seconds: float = 30

    _check = field_validator("items", "code", "name")(_check_expression)

    @model_validator(mode="after")
    def _one_source(self):
        if (self.request is None) == (self.static is None):
            raise ValueError("products needs either a request or a static list")
        return self


class FeasibilitySpec(_Strict):
    request: RequestTemplate
    batch_size: int = Field(1, ge=1, le=500)
    timeout_seconds: float = Field(30, gt=0, le=300)
    retries: int = Field(2, ge=0, le=5)
    # How answers come back: one site per call ("single") or a list in request order.
    sites: str = "@"  # JMESPath: the list of per-site answers ("@" with batch_size 1 is the body)
    site_match: Literal["single", "position"] = "single"
    answers: str  # JMESPath on one site's answer: the list of product answers
    product: str  # JMESPath on one product answer: its code
    # When one product answers per variant (Vodacom: per access medium), the list of variants
    # in a product answer. The rules, variant, bandwidths and note then read each variant.
    variants: str | None = None
    variant: str | None = None  # e.g. Vodacom's access medium id
    variant_name: str | None = None
    variant_type_rules: list[TypeRule] = []  # when the variant decides the product type
    status_rules: list[StatusRule]
    default_status: Status = Status.NOT_AVAILABLE
    # A product that was asked for but isn't in the answer.
    absent_status: Status = Status.NOT_AVAILABLE
    bandwidths: str | None = None  # JMESPath: a list of "lo-hi", numbers or "n" strings
    note: str | None = None

    _check = field_validator(
        "sites", "answers", "product", "variants", "variant", "variant_name", "bandwidths", "note"
    )(_check_expression)

    @model_validator(mode="after")
    def _sites_match_batches(self):
        if self.batch_size > 1 and self.site_match != "position":
            raise ValueError("a batch of more than one site needs site_match 'position'")
        return self


class Schedule(_Strict):
    operation: Literal["sync_products", "test_connection"]
    every_hours: int = Field(ge=1, le=24 * 30)


class ConnectorSpec(_Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=50)
    name: str
    description: str = ""
    capabilities: list[Literal["feasibility"]] = ["feasibility"]
    base_url: str | None = None
    fields: list[ConnectionField] = []
    auth: list[AuthPlacement] = []
    products: ProductsSpec | None = None
    feasibility: FeasibilitySpec | None = None
    errors: list[ErrorRule] = []
    # Provider limits, per connection. Hatchet enforces both (feasibilities/tasks.py).
    max_concurrency: int = Field(2, ge=1, le=50)
    requests_per_minute: int = Field(60, ge=1, le=6000)
    schedules: list[Schedule] = []
    # How "Test connection" proves the credentials: fetch the catalogue, or check one site (for
    # a provider whose catalogue is a static list). The test site is a public city centre.
    test_with: Literal["products", "feasibility"] = "products"
    test_site: tuple[float, float] = (-26.2041, 28.0473)
    # The escape hatch: a connector class under apps.integrations.connectors.
    python: str | None = None
    # Only offered where INTEGRATIONS_DEMO_ENABLED is set (the Demo connector).
    demo: bool = False

    @field_validator("base_url")
    @classmethod
    def _https_only(cls, value):
        if value is None:
            return value
        url = urlparse(value)
        if url.scheme != "https" or not url.netloc or url.query or url.fragment:
            raise ValueError("base_url must be a plain https:// address")
        return value.rstrip("/")

    @field_validator("python")
    @classmethod
    def _our_connectors_only(cls, value):
        if value is not None and not value.startswith(PYTHON_CONNECTORS):
            raise ValueError(f"a Python connector must live under {PYTHON_CONNECTORS}")
        return value

    @model_validator(mode="after")
    def _consistent(self):
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("field keys must be unique")
        secrets = {f.key for f in self.fields if f.secret}
        for placement in self.auth:
            if placement.field not in secrets:
                raise ValueError(f"auth uses {placement.field!r}, which isn't a secret field")
        if self.python is None:
            if self.base_url is None:
                raise ValueError("base_url is required unless the connector is Python")
            if self.products is None or self.feasibility is None:
                raise ValueError("products and feasibility are required")
        return self

    @property
    def secret_keys(self) -> set[str]:
        return {f.key for f in self.fields if f.secret}

    @property
    def setting_keys(self) -> set[str]:
        return {f.key for f in self.fields if not f.secret}

    @property
    def batch_size(self) -> int:
        return self.feasibility.batch_size if self.feasibility else 1
