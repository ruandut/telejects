"""Runs connectors: a definition (spec.py) over HTTP, or a Python class from connectors/.

`build_connector(spec, settings, secrets)` gives an object with `list_products()`, `check()`
and `test_connection()`, all speaking the canonical model (canonical.py) and raising
ConnectorError. Secrets go only where the definition's auth block puts them, and every recorded
request and answer has them redacted.
"""

import importlib
import time
from decimal import Decimal
from typing import Any, Protocol

import httpx
import jmespath
from jmespath import functions

from .canonical import (
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
from .spec import ConnectorSpec, RequestTemplate, TypeRule
from .templating import TemplateError, render

REDACTED = "[redacted]"


class _Functions(functions.Functions):
    """JMESPath's built-ins, plus case folding (providers disagree on "Yes" vs "yes")."""

    @functions.signature({"types": ["string", "null"]})
    def _func_lower(self, value):
        return (value or "").lower()

    @functions.signature({"types": ["string", "null"]})
    def _func_upper(self, value):
        return (value or "").upper()


_OPTIONS = jmespath.Options(custom_functions=_Functions())


def search(expression: str | None, data: Any) -> Any:
    if expression is None:
        return None
    return jmespath.search(expression, data, options=_OPTIONS)


def truthy(value: Any) -> bool:
    """JMESPath's idea of true: everything but null, false and empty strings, lists and maps."""
    return value not in (None, False, "", [], {})


def parse_bandwidth(value: Any) -> tuple[int | None, int | None] | None:
    """ "0-50" -> (0, 50); "1000" or 1000 -> (1000, 1000). Anything else is skipped."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return int(value), int(value)
    text = str(value).strip()
    low, _, high = text.partition("-")
    try:
        low_n = int(float(low)) if low.strip() else None
        high_n = int(float(high)) if high.strip() else low_n
    except ValueError:
        return None
    if low_n is None and high_n is None:
        return None
    return low_n, high_n


def first_type(rules: list[TypeRule], data: Any, default: ProductType | None) -> ProductType | None:
    for rule in rules:
        if truthy(search(rule.when, data)):
            return rule.type
    return default


class Connector(Protocol):
    spec: ConnectorSpec

    def list_products(self) -> tuple[list[ProductInfo], list[CallRecord]]: ...

    def check(self, sites: list[SiteQuery], products: list[ProductRef]) -> CheckOutcome: ...

    def test_connection(self) -> None: ...


def build_connector(
    spec: ConnectorSpec,
    settings: dict,
    secrets: dict,
    client: httpx.Client | None = None,
    recorder=None,
) -> Connector:
    """`recorder`, when given, is called with every exchange (a CallRecord), whether it worked
    or not, after secrets are redacted."""
    if spec.python:
        module_name, _, class_name = spec.python.rpartition(".")
        cls = getattr(importlib.import_module(module_name), class_name)
        return cls(spec, settings, secrets, recorder=recorder)
    return DefinedConnector(spec, settings, secrets, client, recorder=recorder)


class Redactor:
    def __init__(self, secrets: dict):
        self.values = [str(v) for v in secrets.values() if v not in (None, "")]

    def __call__(self, data: Any) -> Any:
        if not self.values:
            return data
        if isinstance(data, str):
            for value in self.values:
                data = data.replace(value, REDACTED)
            return data
        if isinstance(data, list):
            return [self(item) for item in data]
        if isinstance(data, dict):
            return {self(k): self(v) for k, v in data.items()}
        return data


class DefinedConnector:
    """A provider described by its definition."""

    def __init__(
        self, spec: ConnectorSpec, settings: dict, secrets: dict, client=None, recorder=None
    ):
        self.spec = spec
        self.settings = dict(settings)
        self.secrets = dict(secrets)
        self.redact = Redactor(self.secrets)
        self.client = client or httpx.Client(follow_redirects=False)
        self.recorder = recorder

    def _report(self, record: CallRecord, started: float, error: ConnectorError | None = None):
        record.duration_ms = int((time.monotonic() - started) * 1000)
        if error is not None:
            record.error_kind = error.kind
            record.error = self.redact(error.message)
        if self.recorder is not None:
            self.recorder(record)

    # --- HTTP ------------------------------------------------------------------------------

    def _call(self, template: RequestTemplate, context: dict, timeout: float):
        try:
            query = render(template.query, context)
            headers = render(template.headers, context)
            body = render(template.body, context)
            path = render(template.path, context)
        except TemplateError as error:
            detail = f"The definition is wrong: {error}"
            raise ConnectorError(ErrorKind.BAD_REQUEST, detail) from None
        query = {k: v for k, v in query.items() if v is not None}
        for placement in self.spec.auth:
            value = self.secrets.get(placement.field, "")
            if placement.location == "header":
                headers[placement.name] = value
            elif placement.location == "query":
                query[placement.name] = value
            else:
                if body is None:
                    body = {}
                if not isinstance(body, dict):
                    raise ConnectorError(ErrorKind.BAD_REQUEST, "The definition is wrong.")
                body[placement.name] = value
        url = f"{self.spec.base_url}/{str(path).lstrip('/')}" if path else self.spec.base_url
        record = CallRecord(
            request=self.redact(
                {
                    "method": template.method,
                    "url": url,
                    "query": query,
                    "headers": headers,
                    "body": body,
                }
            )
        )
        started = time.monotonic()
        try:
            response = self.client.request(
                template.method,
                url,
                params=query or None,
                headers=headers,
                json=body if template.method == "POST" else None,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            error = ConnectorError(ErrorKind.TIMEOUT)
            self._report(record, started, error)
            raise error from None
        except httpx.HTTPError:
            error = ConnectorError(ErrorKind.PROVIDER_DOWN)
            self._report(record, started, error)
            raise error from None
        record.status_code = response.status_code
        record.response_headers = self.redact(dict(response.headers))
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        record.response = self.redact(parsed if parsed is not None else response.text)
        try:
            self._raise_for(response.status_code, parsed)
            if parsed is None:
                raise ConnectorError(ErrorKind.BAD_RESPONSE, "It wasn't JSON.")
        except ConnectorError as error:
            self._report(record, started, error)
            raise
        self._report(record, started)
        return parsed, record

    def _raise_for(self, status_code: int, body: Any) -> None:
        for rule in self.spec.errors:
            if rule.http_status is not None and rule.http_status != status_code:
                continue
            if rule.when is not None and not truthy(search(rule.when, body)):
                continue
            if rule.http_status is None and rule.when is None:
                continue
            detail = search(rule.detail, body) if rule.detail else None
            raise ConnectorError(rule.kind, self.redact(str(detail)) if detail else "")
        if status_code in (401, 403):
            raise ConnectorError(ErrorKind.AUTH)
        if status_code == 429:
            raise ConnectorError(ErrorKind.RATE_LIMITED)
        if status_code >= 500:
            raise ConnectorError(ErrorKind.PROVIDER_DOWN, f"(HTTP {status_code})")
        if status_code >= 400:
            raise ConnectorError(ErrorKind.BAD_REQUEST, f"(HTTP {status_code})")

    def _context(self, sites: list[SiteQuery] = (), products: list[ProductRef] = ()) -> dict:
        site_contexts = [site.as_context() for site in sites]
        return {
            "site": site_contexts[0] if site_contexts else {},
            "sites": site_contexts,
            "products": [{"code": p.code, "name": p.name} for p in products],
            "product_codes": [p.code for p in products],
            # For providers whose product ids are numbers.
            "product_numbers": [int(p.code) for p in products if p.code.lstrip("-").isdigit()],
            "settings": self.settings,
        }

    # --- products ----------------------------------------------------------------------------

    def list_products(self) -> tuple[list[ProductInfo], list[CallRecord]]:
        spec = self.spec.products
        calls = []
        if spec.static is not None:
            body: Any = spec.static
        else:
            body, record = self._call(spec.request, self._context(), spec.timeout_seconds)
            calls.append(record)
        items = search(spec.items, body)
        if not isinstance(items, list):
            raise ConnectorError(ErrorKind.BAD_RESPONSE, "No product list in the answer.")
        found: dict[str, ProductInfo] = {}
        for item in items:
            code = search(spec.code, item)
            if code in (None, ""):
                continue
            code = str(code)
            name = search(spec.name, item)
            found.setdefault(
                code,
                ProductInfo(
                    code=code,
                    name=str(name) if name not in (None, "") else code,
                    product_type=first_type(spec.type_rules, item, spec.default_type),
                    raw=self.redact(item),
                ),
            )
        return list(found.values()), calls

    # --- feasibility -------------------------------------------------------------------------

    def check(self, sites: list[SiteQuery], products: list[ProductRef]) -> CheckOutcome:
        spec = self.spec.feasibility
        outcome = CheckOutcome(answers=[])
        for start in range(0, len(sites), spec.batch_size):
            batch = sites[start : start + spec.batch_size]
            body, record = self._call(
                spec.request, self._context(batch, products), spec.timeout_seconds
            )
            outcome.calls.append(record)
            outcome.answers += self._read_answers(body, batch, products)
        return outcome

    def _read_answers(self, body, batch: list[SiteQuery], products: list[ProductRef]):
        spec = self.spec.feasibility
        if spec.site_match == "single":
            site_items = [search(spec.sites, body)]
        else:
            site_items = search(spec.sites, body)
            if not isinstance(site_items, list) or len(site_items) != len(batch):
                raise ConnectorError(
                    ErrorKind.BAD_RESPONSE, "The answer doesn't have one entry per site."
                )
        wanted = {p.code for p in products}
        answers = []
        for site, item in zip(batch, site_items, strict=True):
            seen = set()
            entries = search(spec.answers, item) if item is not None else None
            for entry in entries if isinstance(entries, list) else []:
                code = search(spec.product, entry)
                if code in (None, "") or str(code) not in wanted:
                    continue
                code = str(code)
                if spec.variants is None:
                    seen.add(code)
                    answers.append(self._answer(site, code, entry))
                    continue
                variants = search(spec.variants, entry)
                for variant in variants if isinstance(variants, list) else []:
                    seen.add(code)
                    answers.append(self._answer(site, code, variant))
            for code in wanted - seen:
                answers.append(Answer(site.ref, code, spec.absent_status))
        return answers

    def _answer(self, site: SiteQuery, code: str, entry: Any) -> Answer:
        spec = self.spec.feasibility
        status = spec.default_status
        for rule in spec.status_rules:
            if truthy(search(rule.when, entry)):
                status = rule.status
                break
        raw_bandwidths = search(spec.bandwidths, entry) if spec.bandwidths else None
        if raw_bandwidths is not None and not isinstance(raw_bandwidths, list):
            raw_bandwidths = [raw_bandwidths]
        bandwidths = [b for b in map(parse_bandwidth, raw_bandwidths or []) if b is not None]
        variant = search(spec.variant, entry) if spec.variant else None
        variant_name = search(spec.variant_name, entry) if spec.variant_name else None
        note = search(spec.note, entry) if spec.note else None
        return Answer(
            site_ref=site.ref,
            product_code=code,
            status=Status(status),
            variant_code="" if variant is None else str(variant),
            variant_name="" if variant_name is None else str(variant_name),
            product_type=first_type(spec.variant_type_rules, entry, None),
            bandwidths=bandwidths,
            note="" if note is None else str(note)[:255],
        )

    # --- health ------------------------------------------------------------------------------

    def test_connection(self) -> None:
        if self.spec.test_with == "products" and self.spec.products.request is not None:
            self.list_products()
            return
        latitude, longitude = self.spec.test_site
        site = SiteQuery("test", "Test site", Decimal(str(latitude)), Decimal(str(longitude)))
        products, _ = self.list_products()
        refs = [ProductRef(p.code, p.name, p.product_type) for p in products[:1]]
        self.check([site], refs)


def timed(func, *args):
    """(result, milliseconds)."""
    start = time.monotonic()
    result = func(*args)
    return result, int((time.monotonic() - start) * 1000)
