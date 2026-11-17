"""Everything that changes feasibility runs. Views and tasks only call these.

A run goes: created with its sites (the request) -> planned into provider checks and handed to
Hatchet (`plan_run`, in the worker) -> each check calls its provider and writes its sites'
results as soon as it finishes (`perform_check`) -> completed when no check is open. Every step
publishes an event naming the run and the sites that changed, so open tabs see each line as it
finishes (live.py).
"""

import logging
import time
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.integrations import services as integrations
from apps.integrations.canonical import ConnectorError, ErrorKind, ProductRef, SiteQuery
from apps.integrations.models import Connection, ProviderProduct
from apps.realms import events
from apps.realms.models import Realm

from .models import FeasibilityResult, FeasibilityRun, ProviderCheck, RunSite

logger = logging.getLogger(__name__)

MAX_ROWS = 10_000
MAX_COLUMNS = 50
PLACES = Decimal("0.0000001")
RUNS_TOPIC = "feasibility_runs"
RUN_TOPIC = "feasibility_run"

RunStatus = FeasibilityRun.Status
CheckStatus = ProviderCheck.Status


def _after_commit(func) -> None:
    """Run once the surrounding transaction commits. A seam the tests replace."""
    transaction.on_commit(func)


def _enqueue_plan(realm_id: int, run_id: int) -> None:
    from .tasks import RunInput, plan_feasibility_run

    plan_feasibility_run.run_no_wait(RunInput(realm_id=realm_id, run_id=run_id))


def _enqueue_checks(realm_id: int, run_id: int, check_ids: list[int]) -> None:
    from .tasks import enqueue_checks

    enqueue_checks(realm_id, run_id, check_ids)


def _publish(run: FeasibilityRun, site_ids=()) -> None:
    events.publish(run.realm_id, RUNS_TOPIC)
    events.publish(run.realm_id, RUN_TOPIC, subject=run.id, items=list(site_ids))


# --- starting a run ---------------------------------------------------------------------------


def _coordinate(value, low: int, high: int) -> Decimal | None:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation, ValueError, TypeError:
        return None
    if not number.is_finite() or not low <= number <= high:
        return None
    return number.quantize(PLACES, rounding=ROUND_HALF_UP)


def row_problems(row: dict) -> list[str]:
    """Why a row can't be checked (the portal shows the same reasons before starting)."""
    problems = []
    name = str(row.get("name") or "").strip()
    if not name:
        problems.append("No name.")
    elif len(name) > 100:
        problems.append("The name is longer than 100 characters.")
    if _coordinate(row.get("latitude"), -90, 90) is None:
        problems.append("The latitude isn't a number from -90 to 90.")
    if _coordinate(row.get("longitude"), -180, 180) is None:
        problems.append("The longitude isn't a number from -180 to 180.")
    return problems


def _clean_rows(rows) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"rows": "There are no sites to check."})
    if len(rows) > MAX_ROWS:
        raise ValidationError({"rows": f"A run can check up to {MAX_ROWS:,} sites."})
    errors, seen, clean = {}, set(), []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors[str(index)] = ["Not a row."]
            continue
        line = row.get("line_number")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            errors[str(index)] = ["No line number."]
            continue
        if line in seen:
            errors[str(line)] = ["The same line number twice."]
            continue
        seen.add(line)
        if problems := row_problems(row):
            errors[str(line)] = problems
            continue
        extra = row.get("row") or {}
        if not isinstance(extra, dict) or len(extra) > MAX_COLUMNS:
            errors[str(line)] = ["The row's columns couldn't be read."]
            continue
        clean.append(
            {
                "line_number": line,
                "name": str(row["name"]).strip(),
                "latitude": _coordinate(row["latitude"], -90, 90),
                "longitude": _coordinate(row["longitude"], -180, 180),
                "row": {
                    str(k)[:100]: str(v if v is not None else "")[:500] for k, v in extra.items()
                },
            }
        )
    if errors:
        raise ValidationError({"rows": errors})
    return clean


@transaction.atomic
def start_run(
    realm: Realm,
    created_by,
    *,
    name: str,
    products: list[ProviderProduct],
    rows: list,
    columns: list | None = None,
    mapping: dict | None = None,
) -> FeasibilityRun:
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise ValidationError({"name": "Give the run a name of up to 100 characters."})
    if not products:
        raise ValidationError({"products": "Pick at least one product."})
    usable = {
        p.id
        for p in ProviderProduct.objects.in_realm(realm)
        .current()
        .filter(id__in=[p.id for p in products])
    }
    if any(p.id not in usable or p.realm_id != realm.id for p in products):
        raise ValidationError({"products": "Pick products your company's connections offer."})
    clean = _clean_rows(rows)
    columns = [str(c)[:100] for c in (columns or [])][:MAX_COLUMNS]
    run = FeasibilityRun.objects.create(
        realm=realm,
        name=name,
        created_by=created_by,
        columns=columns,
        mapping={k: str(v)[:100] for k, v in (mapping or {}).items() if isinstance(k, str)},
        site_count=len(clean),
    )
    run.products.set(products)
    RunSite.objects.bulk_create(
        [RunSite(realm=realm, run=run, **row) for row in clean], batch_size=1000
    )
    _publish(run)
    realm_id, run_id = realm.id, run.id
    _after_commit(lambda: _enqueue_plan(realm_id, run_id))
    return run


# --- planning (worker) ------------------------------------------------------------------------


@transaction.atomic
def plan_run(realm_id: int, run_id: int) -> list[int]:
    """Make the run's provider checks: per connection, its unique coordinates in batches of the
    connector's size. Returns the ids of the checks to hand to Hatchet."""
    run = FeasibilityRun.objects.in_realm_id(realm_id).select_for_update().by_id(run_id)
    if run is None or run.status != RunStatus.QUEUED:
        return []
    sites = list(RunSite.objects.in_realm_id(realm_id).of_run(run).order_by("line_number"))
    by_coordinates: dict[tuple, list[RunSite]] = defaultdict(list)
    for site in sites:
        by_coordinates[site.coordinates].append(site)
    connections = {
        p.connection_id: p.connection for p in run.products.all().select_related("connection")
    }
    check_ids = []
    through = ProviderCheck.sites.through
    links = []
    for connection in sorted(connections.values(), key=lambda c: c.id):
        definition = connection.definition()
        batch_size = definition.parsed.batch_size if definition else 1
        groups = list(by_coordinates.values())
        for start in range(0, len(groups), batch_size):
            check = ProviderCheck.objects.create(realm_id=realm_id, run=run, connection=connection)
            check_ids.append(check.id)
            for group in groups[start : start + batch_size]:
                links += [through(providercheck_id=check.id, runsite_id=s.id) for s in group]
    through.objects.bulk_create(links, batch_size=2000)
    run.status = RunStatus.RUNNING
    run.started_at = timezone.now()
    run.checks_total = len(check_ids)
    run.save()
    _publish(run)
    if not check_ids:
        _complete_if_finished(run.id, realm_id)
    return check_ids


def runtime_for(realm_id: int, check_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    """check id -> (connection id, max concurrency, requests per minute), for Hatchet's limits."""
    found = {}
    checks = ProviderCheck.objects.in_realm_id(realm_id).filter(id__in=check_ids)
    specs = {}
    for check in checks.select_related("connection"):
        key = check.connection.connector_key
        if key not in specs:
            definition = check.connection.definition()
            specs[key] = definition.parsed if definition else None
        spec = specs[key]
        found[check.id] = (
            check.connection_id,
            spec.max_concurrency if spec else 1,
            spec.requests_per_minute if spec else 30,
        )
    return found


# --- one provider call (worker) ---------------------------------------------------------------


def _claim(realm_id: int, check_id: int) -> ProviderCheck | None:
    with transaction.atomic():
        check = (
            ProviderCheck.objects.in_realm_id(realm_id)
            .select_for_update()
            .select_related("run", "connection")
            .by_id(check_id)
        )
        if check is None or check.status != CheckStatus.PENDING:
            return None
        if check.run.status != RunStatus.RUNNING:
            return None
        check.status = CheckStatus.RUNNING
        check.started_at = timezone.now()
        check.save(update_fields=["status", "started_at"])
        return check


def _sleep(seconds: float) -> None:
    """A seam the tests replace."""
    time.sleep(seconds)


def perform_check(realm_id: int, check_id: int) -> str:
    """Call the provider for one check and write what it said. Returns the check's status."""
    check = _claim(realm_id, check_id)
    if check is None:
        return "skipped"
    run, connection = check.run, check.connection
    sites = list(check.sites.order_by("line_number", "id"))
    groups: dict[tuple, list[RunSite]] = defaultdict(list)
    for site in sites:
        groups[site.coordinates].append(site)
    queries = [
        SiteQuery(ref=str(group[0].id), name=group[0].name, latitude=lat, longitude=lon)
        for (lat, lon), group in groups.items()
    ]
    by_ref = {str(group[0].id): group for group in groups.values()}
    products = list(run.products.filter(connection_id=connection.id).order_by("id"))
    refs = [ProductRef(p.code, p.name) for p in products]
    started = time.monotonic()
    outcome, error, version = None, None, None
    try:
        connector, definition = integrations.connector_for(connection)
        version = definition.version
        retries = definition.parsed.feasibility.retries if definition.parsed.feasibility else 0
        for attempt in range(retries + 1):
            check.attempts += 1
            try:
                outcome = connector.check(queries, refs)
                error = None
                break
            except ConnectorError as failure:
                error = failure
                if not failure.retryable or attempt == retries:
                    break
                wait = 10 * (attempt + 1) if failure.kind == ErrorKind.RATE_LIMITED else 2**attempt
                _sleep(wait)
    except ConnectorError as failure:
        error = failure
    duration = int((time.monotonic() - started) * 1000)
    if error is not None:
        _fail(check, error, version, duration)
        if error.kind == ErrorKind.AUTH:
            _refused(check, error)
        return CheckStatus.FAILED
    _succeed(check, outcome, by_ref, products, version, duration)
    return CheckStatus.DONE


@transaction.atomic
def _succeed(check, outcome, by_ref, products, version, duration) -> None:
    by_code = {p.code: p for p in products}
    results = []
    for answer in outcome.answers:
        product = by_code.get(answer.product_code)
        group = by_ref.get(answer.site_ref)
        if product is None or group is None:
            continue
        for site in group:
            results.append(
                FeasibilityResult(
                    realm_id=check.realm_id,
                    run_id=check.run_id,
                    site=site,
                    check_run=check,
                    product=product,
                    variant_code=answer.variant_code[:100],
                    variant_name=answer.variant_name[:255],
                    product_type=answer.product_type or product.product_type,
                    status=answer.status,
                    bandwidths=[list(b) for b in answer.bandwidths],
                    note=answer.note[:255],
                )
            )
    FeasibilityResult.objects.bulk_create(results, batch_size=1000)
    check.status = CheckStatus.DONE
    check.definition_version = version
    check.duration_ms = duration
    check.finished_at = timezone.now()
    check.calls = [
        {"request": c.request, "status": c.status_code, "response": c.response}
        for c in outcome.calls
    ]
    check.save()
    _count(check, "checks_done")


@transaction.atomic
def _fail(check, error: ConnectorError, version, duration) -> None:
    check.status = CheckStatus.FAILED
    check.error_kind = error.kind
    check.error = error.message[:500]
    check.definition_version = version
    check.duration_ms = duration
    check.finished_at = timezone.now()
    check.save()
    _count(check, "checks_failed")


def _refused(check: ProviderCheck, error: ConnectorError) -> None:
    """The provider refused the credentials: the connection is failing, and this run's other
    calls with it fail now instead of trying."""
    connection = Connection.objects.in_realm_id(check.realm_id).by_id(check.connection_id)
    if connection is not None:
        integrations.mark_credentials_refused(connection, error)
    with transaction.atomic():
        others = list(
            ProviderCheck.objects.in_realm_id(check.realm_id)
            .select_for_update()
            .of_run(check.run_id)
            .filter(connection_id=check.connection_id, status=CheckStatus.PENDING)
        )
        for other in others:
            other.status = CheckStatus.FAILED
            other.error_kind = error.kind
            other.error = error.message[:500]
            other.finished_at = timezone.now()
            other.save()
            _count(other, "checks_failed")


def _count(check: ProviderCheck, counter: str) -> None:
    """Move the run's counters, tell open tabs which sites changed, and finish the run when
    nothing is left."""
    FeasibilityRun.objects.in_realm_id(check.realm_id).filter(pk=check.run_id).update(
        **{counter: F(counter) + 1}
    )
    run = FeasibilityRun.objects.in_realm_id(check.realm_id).get(pk=check.run_id)
    _publish(run, check.sites.values_list("id", flat=True))
    _complete_if_finished(run.id, run.realm_id)


def _complete_if_finished(run_id: int, realm_id: int) -> None:
    runs = FeasibilityRun.objects.in_realm_id(realm_id).filter(pk=run_id)
    run = runs.first()
    if run is None or run.status != RunStatus.RUNNING:
        return
    if ProviderCheck.objects.in_realm_id(realm_id).of_run(run_id).open().exists():
        return
    # Conditional, so two checks finishing together complete the run once.
    if runs.filter(status=RunStatus.RUNNING).update(
        status=RunStatus.COMPLETED, finished_at=timezone.now()
    ):
        _publish(run)


# --- cancelling and retrying ------------------------------------------------------------------


@transaction.atomic
def cancel_run(run: FeasibilityRun) -> FeasibilityRun:
    run = FeasibilityRun.objects.in_realm(run.realm_id).select_for_update().get(pk=run.pk)
    if not run.is_going:
        raise ValidationError({"detail": "Only a run that is still going can be cancelled."})
    pending = (
        ProviderCheck.objects.in_realm(run.realm_id).of_run(run).filter(status=CheckStatus.PENDING)
    )
    site_ids = set(
        RunSite.objects.in_realm(run.realm_id)
        .filter(checks__in=pending)
        .values_list("id", flat=True)
    )
    cancelled = pending.update(status=CheckStatus.CANCELLED, finished_at=timezone.now())
    run.status = RunStatus.CANCELLED
    run.finished_at = timezone.now()
    run.checks_cancelled = F("checks_cancelled") + cancelled
    run.save()
    run.refresh_from_db()
    _publish(run, site_ids)
    return run


@transaction.atomic
def retry_failed(run: FeasibilityRun) -> FeasibilityRun:
    run = FeasibilityRun.objects.in_realm(run.realm_id).select_for_update().get(pk=run.pk)
    if run.status != RunStatus.COMPLETED:
        raise ValidationError({"detail": "Failed checks can be retried once the run is done."})
    failed = list(
        ProviderCheck.objects.in_realm(run.realm_id).of_run(run).filter(status=CheckStatus.FAILED)
    )
    if not failed:
        raise ValidationError({"detail": "Nothing failed in this run."})
    ids = [c.id for c in failed]
    ProviderCheck.objects.in_realm(run.realm_id).filter(id__in=ids).update(
        status=CheckStatus.PENDING, error="", error_kind="", finished_at=None
    )
    run.status = RunStatus.RUNNING
    run.finished_at = None
    run.checks_failed = F("checks_failed") - len(ids)
    run.save()
    run.refresh_from_db()
    site_ids = (
        RunSite.objects.in_realm(run.realm_id)
        .filter(checks__id__in=ids)
        .values_list("id", flat=True)
    )
    _publish(run, set(site_ids))
    realm_id, run_id = run.realm_id, run.id
    _after_commit(lambda: _enqueue_checks(realm_id, run_id, ids))
    return run
