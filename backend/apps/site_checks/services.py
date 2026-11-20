"""Everything that changes one-site checks. Views and tasks only call these.

A check is made with one call per provider (`start_check`), each handed to Hatchet ahead of bulk
work and limited like it (tasks.py). The caller then waits (`wait_for`) until every call has
answered or its time is up; calls still going carry on and write their results when they finish.
"""

import logging
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.integrations import services as integrations
from apps.integrations.canonical import ConnectorError, ProductRef, SiteQuery, Status
from apps.integrations.models import Connection, ProviderProduct

from .models import SiteCheck, SiteCheckCall, SiteCheckResult

logger = logging.getLogger(__name__)

PLACES = Decimal("0.0000001")
POLL_SECONDS = 0.2

CallStatus = SiteCheckCall.Status


@dataclass(frozen=True)
class Skipped:
    """A provider asked for that wasn't called, and why."""

    connector_key: str
    kind: str  # "NotConnected" or "NotOffered"
    message: str


def _after_commit(func) -> None:
    """Run once the surrounding transaction commits. A seam the tests replace."""
    transaction.on_commit(func)


def _enqueue_calls(realm_id: int, call_ids: list[int]) -> None:
    from .tasks import enqueue_calls

    enqueue_calls(realm_id, call_ids)


def _sleep(seconds: float) -> None:
    """A seam the tests replace."""
    time.sleep(seconds)


def _now() -> float:
    """A seam the tests replace."""
    return time.monotonic()


def connection_for(realm_id: int, connector_key: str) -> Connection | None:
    """The company's connection a one-site check uses for a provider: its oldest enabled one."""
    return (
        Connection.objects.in_realm_id(realm_id)
        .enabled()
        .filter(connector_key=connector_key)
        .order_by("id")
        .first()
    )


def start_check(
    realm_id: int,
    *,
    latitude,
    longitude,
    wanted: dict[str, list[str]],
    timeout: int,
    user=None,
    api_client_id: int | None = None,
) -> tuple[SiteCheck, list[Skipped]]:
    """Ask each provider in `wanted` (connector key -> product codes) about one place.

    A provider the company has no enabled connection for, or whose connection doesn't offer
    any of the products, isn't called; it is returned in the skipped list instead."""
    skipped: list[Skipped] = []
    plans: list[tuple[Connection, list[ProviderProduct]]] = []
    for key, codes in wanted.items():
        connection = connection_for(realm_id, key)
        if connection is None:
            skipped.append(Skipped(key, "NotConnected", f"Not connected to {key}."))
            continue
        products = list(
            ProviderProduct.objects.in_realm_id(realm_id)
            .current()
            .filter(connection=connection, code__in=codes)
            .order_by("id")
        )
        if not products:
            skipped.append(
                Skipped(key, "NotOffered", f"{connection.name} doesn't offer these products.")
            )
            continue
        plans.append((connection, products))
    with transaction.atomic():
        check = SiteCheck.objects.create(
            realm_id=realm_id,
            latitude=Decimal(str(latitude)).quantize(PLACES, ROUND_HALF_UP),
            longitude=Decimal(str(longitude)).quantize(PLACES, ROUND_HALF_UP),
            timeout_seconds=timeout,
            requested_by=user,
            api_client_id=api_client_id,
        )
        call_ids = []
        for connection, products in plans:
            call = SiteCheckCall.objects.create(
                realm_id=realm_id,
                site_check=check,
                connection=connection,
                connector_key=connection.connector_key,
            )
            call.products.set(products)
            call_ids.append(call.id)
        if call_ids:
            _after_commit(lambda: _enqueue_calls(realm_id, call_ids))
    return check, skipped


def wait_for(check: SiteCheck, timeout: float) -> list[SiteCheckCall]:
    """Wait until every call has answered or `timeout` seconds have passed. Returns the calls."""
    deadline = _now() + timeout
    calls = SiteCheckCall.objects.in_realm_id(check.realm_id).of_check(check)
    while calls.open().exists() and _now() < deadline:
        _sleep(POLL_SECONDS)
    return list(calls.order_by("id"))


def runtime_for(realm_id: int, call_ids: list[int]) -> dict[int, tuple[str, int, int]]:
    """call id -> (limit key, max concurrency, requests per minute): the same limits as bulk
    checks, so one-site checks share a platform account's limits too (0004)."""
    found = {}
    calls = SiteCheckCall.objects.in_realm_id(realm_id).filter(id__in=call_ids)
    for call in calls.select_related("connection"):
        if call.connection is None:
            continue
        definition = call.connection.definition()
        spec = definition.parsed if definition else None
        found[call.id] = (
            call.connection.limit_key,
            spec.max_concurrency if spec else 1,
            spec.requests_per_minute if spec else 30,
        )
    return found


def _claim(realm_id: int, call_id: int) -> SiteCheckCall | None:
    with transaction.atomic():
        call = (
            SiteCheckCall.objects.in_realm_id(realm_id)
            .select_for_update(of=("self",))
            .select_related("site_check", "connection")
            .filter(pk=call_id)
            .first()
        )
        if call is None or call.status != CallStatus.PENDING or call.connection is None:
            return None
        call.status = CallStatus.RUNNING
        call.started_at = timezone.now()
        call.save(update_fields=["status", "started_at"])
        return call


def perform_call(realm_id: int, call_id: int) -> str:
    """Ask one provider about the place, once, and write what it said. Returns the status.

    No retries: someone is waiting, and Rapid didn't retry one-site checks either."""
    call = _claim(realm_id, call_id)
    if call is None:
        return "skipped"
    check, connection = call.site_check, call.connection
    products = list(call.products.order_by("id"))
    usage = integrations.usage_of(connection)
    call.credentials = usage["credentials"]
    call.platform_account_id = usage["platform_account_id"]
    recorder = integrations.recorder_for(connection, "check_feasibility", site_check_id=check.id)
    started = time.monotonic()
    query = SiteQuery(
        ref=str(check.id), name="", latitude=check.latitude, longitude=check.longitude
    )
    try:
        connector, definition = integrations.connector_for(connection, recorder)
        call.definition_version = definition.version
        outcome = connector.check([query], [ProductRef(p.code, p.name) for p in products])
    except ConnectorError as error:
        _finish(call, started, error=error)
        return CallStatus.FAILED
    except Exception:
        logger.exception("One-site check call %s failed unexpectedly", call.id)
        _finish(call, started, error=ConnectorError("bad_response"))
        return CallStatus.FAILED
    _write_results(call, outcome, products)
    _finish(call, started)
    return CallStatus.DONE


@transaction.atomic
def _write_results(call: SiteCheckCall, outcome, products: list[ProviderProduct]) -> None:
    by_code = {p.code: p for p in products}
    results = []
    for answer in outcome.answers:
        product = by_code.get(answer.product_code)
        if product is None or answer.status == Status.NOT_AVAILABLE:
            continue
        results.append(
            SiteCheckResult(
                realm_id=call.realm_id,
                site_check_id=call.site_check_id,
                call=call,
                product=product,
                connector_key=call.connector_key,
                product_code=product.code,
                variant_code=answer.variant_code[:100],
                variant_name=answer.variant_name[:255],
                product_type=answer.product_type or product.product_type,
                status=answer.status,
                bandwidths=[list(b) for b in answer.bandwidths],
                note=answer.note[:255],
            )
        )
    SiteCheckResult.objects.bulk_create(results)


def _finish(call: SiteCheckCall, started: float, error: ConnectorError | None = None) -> None:
    call.status = CallStatus.FAILED if error else CallStatus.DONE
    if error is not None:
        call.error_kind = error.kind
        call.error = error.message[:500]
    call.duration_ms = int((time.monotonic() - started) * 1000)
    call.finished_at = timezone.now()
    call.save()
