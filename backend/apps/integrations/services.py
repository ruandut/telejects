"""Everything that changes integrations: the connector catalogue, a company's connections, their
products and their syncs. Views and tasks only call these.

Every function that touches company data takes the company (or a row already looked up inside
it) and stays inside it. Provider calls go through engine.build_connector; nothing else here
talks HTTP.
"""

import logging
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings as django_settings
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.integration_logs.services import Recorder
from apps.realms import events
from apps.realms.models import Realm

from .canonical import ConnectorError, ErrorKind
from .engine import Connector, build_connector
from .models import (
    Connection,
    ConnectorDefinition,
    PlatformAccount,
    PlatformGrant,
    ProviderProduct,
    SyncRun,
)
from .spec import ConnectorSpec

logger = logging.getLogger(__name__)

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TOPIC = "integrations"

Kind = SyncRun.Kind
Trigger = SyncRun.Trigger
Health = Connection.Health


def _after_commit(func) -> None:
    """Run once the surrounding transaction commits. A seam the tests replace."""
    transaction.on_commit(func)


def _enqueue(realm_id: int, connection_id: int, operation: str, trigger: str) -> None:
    from .tasks import OperationInput, run_connection_operation

    run_connection_operation.run_no_wait(
        OperationInput(
            realm_id=realm_id, connection_id=connection_id, operation=operation, trigger=trigger
        )
    )


def _schedule(connection: Connection, operation: str, trigger: str) -> None:
    realm_id, connection_id = connection.realm_id, connection.id
    _after_commit(lambda: _enqueue(realm_id, connection_id, operation, trigger))


# --- the catalogue (platform data) ----------------------------------------------------------


def load_definitions(directory: Path = DEFINITIONS_DIR, user=None) -> list[tuple[str, int, bool]]:
    """Load the built-in definitions. A changed one becomes a new version; an unchanged one is
    left alone. Returns (key, version, whether it is new)."""
    loaded = []
    for path in sorted(directory.glob("*.json")):
        spec = ConnectorSpec.model_validate_json(path.read_text())
        loaded.append(save_definition(spec, user=user))
    return loaded


@transaction.atomic
def save_definition(spec: ConnectorSpec, user=None) -> tuple[str, int, bool]:
    data = spec.model_dump(mode="json", exclude_defaults=True)
    current = ConnectorDefinition.objects.filter(key=spec.key).order_by("-version").first()
    if current is not None and current.spec == data:
        return spec.key, current.version, False
    version = (current.version + 1) if current else 1
    ConnectorDefinition.objects.create(key=spec.key, version=version, spec=data, created_by=user)
    return spec.key, version, True


def available_definitions() -> list[ConnectorDefinition]:
    """What a company may connect: the newest version of each, Demo only where enabled."""
    demo = django_settings.INTEGRATIONS_DEMO_ENABLED
    return [d for d in ConnectorDefinition.objects.latest() if demo or not d.parsed.demo]


def definition_for(key: str) -> ConnectorDefinition:
    for definition in available_definitions():
        if definition.key == key:
            return definition
    raise ValidationError({"connector": "Choose one of the available connectors."})


PLATFORM_UNAVAILABLE = "Telejects' account for this provider isn't available to you any more."
PLATFORM_FAILING = "Telejects' account for this provider is failing; we're on it."
PLATFORM_NOT_ANSWERING = "The provider isn't answering right now; we'll keep trying."


def _may_use(realm_id: int, account: PlatformAccount) -> bool:
    """A company may use a Telejects account that is on, configured in .env, and offered to
    everyone or granted to it."""
    if not account.enabled or not account.configured:
        return False
    if account.available_to_all:
        return True
    return PlatformGrant.objects.in_realm_id(realm_id).of_account(account).exists()


def granted_account(connection: Connection) -> PlatformAccount | None:
    """The platform account a platform connection may use right now, if any."""
    if not connection.uses_platform:
        return None
    account = connection.platform_account
    return account if _may_use(connection.realm_id, account) else None


def accounts_for(realm_id: int) -> list[PlatformAccount]:
    """The Telejects accounts this company may use, oldest first."""
    accounts = PlatformAccount.objects.enabled().order_by("id")
    return [a for a in accounts if _may_use(realm_id, a)]


def credentials_of(connection: Connection) -> PlatformAccount | Connection:
    """Whose account a connection's calls use. The one place that decides it (0004)."""
    if not connection.uses_platform:
        return connection
    account = granted_account(connection)
    if account is None:
        raise ConnectorError(ErrorKind.BAD_REQUEST, PLATFORM_UNAVAILABLE)
    return account


def usage_of(connection: Connection) -> dict:
    """What a provider call records about whose credentials it used."""
    if connection.uses_platform:
        return {"credentials": "platform", "platform_account_id": connection.platform_account_id}
    return {"credentials": "own", "platform_account_id": None}


def recorder_for(connection: Connection, operation: str, **links) -> Recorder:
    """Where a connection's provider calls are logged (0005), with what they belong to
    (`run_id`, `check_id` or `sync_id`). For a platform connection, Telejects' settings are
    hidden too: companies never see them."""
    usage = usage_of(connection)
    hide = []
    if connection.uses_platform and connection.platform_account is not None:
        hide = list(connection.platform_account.settings.values())
    return Recorder(
        realm_id=connection.realm_id,
        operation=operation,
        connection_id=connection.id,
        connection_name=connection.name,
        connector_key=connection.connector_key,
        credentials=usage["credentials"],
        hide=hide,
        **links,
    )


def connector_for(
    connection: Connection, recorder: Recorder | None = None
) -> tuple[Connector, ConnectorDefinition]:
    definition = connection.definition()
    if definition is None:
        raise ConnectorError(ErrorKind.BAD_REQUEST, "Its connector is no longer offered.")
    owner = credentials_of(connection)
    if recorder is not None:
        recorder.definition_version = definition.version
        recorder.secret_header_names = {
            a.name for a in definition.parsed.auth if a.location == "header"
        }
    connector = build_connector(definition.parsed, owner.settings, owner.secrets, recorder=recorder)
    return connector, definition


# --- connections ------------------------------------------------------------------------------


def _split_fields(spec: ConnectorSpec, values: dict, *, current: Connection | None = None):
    """(settings, secrets) from what was filled in. An empty secret keeps the current one."""
    errors = {}
    unknown = set(values) - {f.key for f in spec.fields}
    if unknown:
        errors["fields"] = f"{spec.name} doesn't ask for {', '.join(sorted(unknown))}."
    settings = dict(current.settings) if current else {}
    secrets = current.secrets if current else {}
    for field in spec.fields:
        if field.key in values:
            raw = values[field.key]
            value = "" if raw is None else str(raw).strip()
            if len(value) > 1000:
                errors[field.key] = "That's too long."
                continue
            if field.secret:
                if value:
                    secrets[field.key] = value
            else:
                if field.type == "email" and value and not EMAIL.match(value):
                    errors[field.key] = "Enter a valid email address."
                settings[field.key] = value
        present = secrets.get(field.key) if field.secret else settings.get(field.key)
        if field.required and not present and field.key not in errors:
            errors[field.key] = f"{field.label} is required."
    if errors:
        raise ValidationError(errors)
    return settings, secrets


def _check_name(realm: Realm, name: str, *, exclude: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Give the connection a name."})
    clash = Connection.objects.in_realm(realm).filter(name__iexact=name)
    if exclude is not None:
        clash = clash.exclude(pk=exclude)
    if clash.exists():
        raise ValidationError({"name": "You already have a connection with that name."})
    return name


@transaction.atomic
def connect(realm: Realm, *, connector: str, name: str, fields: dict) -> Connection:
    """Connect a provider with the company's own account, then test it and sync its products."""
    definition = definition_for(connector)
    spec = definition.parsed
    settings, secrets = _split_fields(spec, fields)
    connection = Connection(
        realm=realm,
        name=_check_name(realm, name or spec.name),
        connector_key=definition.key,
        settings=settings,
    )
    connection.secrets = secrets
    connection.save()
    events.publish(realm.id, TOPIC)
    _schedule(connection, "connect", Trigger.CONNECT)
    return connection


@transaction.atomic
def update_connection(
    connection: Connection,
    *,
    name: str | None = None,
    fields: dict | None = None,
    enabled: bool | None = None,
    credentials: str | None = None,
) -> Connection:
    retest = False
    if name is not None:
        connection.name = _check_name(connection.realm, name, exclude=connection.pk)
    if credentials == Connection.Source.PLATFORM and not connection.uses_platform:
        connection.platform_account = _grant_for(connection)
        connection.credentials = Connection.Source.PLATFORM
        # The company's own account is no longer used, so its credentials go.
        connection.settings, connection.secrets = {}, {}
        retest = True
        fields = None
    elif credentials == Connection.Source.OWN and connection.uses_platform:
        definition = connection.definition()
        if definition is None:
            raise ValidationError({"fields": "This connector is no longer offered."})
        connection.settings, connection.secrets = _split_fields(definition.parsed, fields or {})
        connection.credentials = Connection.Source.OWN
        connection.platform_account = None
        retest = True
        fields = None
    elif fields and connection.uses_platform:
        raise ValidationError(
            {"fields": "This connection uses Telejects' account. Switch to your own first."}
        )
    if fields:
        definition = connection.definition()
        if definition is None:
            raise ValidationError({"fields": "This connector is no longer offered."})
        before = (connection.settings, connection.secrets)
        settings, secrets = _split_fields(definition.parsed, fields, current=connection)
        connection.settings = settings
        connection.secrets = secrets
        retest = (settings, secrets) != before
    if enabled is not None:
        if enabled and connection.uses_platform and granted_account(connection) is None:
            raise ValidationError({"enabled": PLATFORM_UNAVAILABLE + " Use your own account."})
        retest = retest or (enabled and not connection.enabled)
        connection.enabled = enabled
    if retest:
        connection.health = Health.UNKNOWN
        connection.health_error = ""
    connection.save()
    events.publish(connection.realm_id, TOPIC)
    if retest and connection.enabled:
        _schedule(connection, "connect", Trigger.MANUAL)
    return connection


def _grant_for(connection: Connection) -> PlatformAccount:
    """The Telejects account this connection's company may use for its provider, or a refusal
    that looks the same whether no account exists or the company just may not use it."""
    for account in accounts_for(connection.realm_id):
        if account.connector_key == connection.connector_key:
            return account
    raise ValidationError({"credentials": "Telejects' account isn't available for this."})


def granted_connectors(realm: Realm) -> set[str]:
    """The connector keys this company may use Telejects' accounts for."""
    return {a.connector_key for a in accounts_for(realm.id)}


# --- every provider, active from the start ------------------------------------------------------


def ensure_platform_accounts() -> list[PlatformAccount]:
    """A Telejects account for every provider configured in .env (its secrets all set) with a
    published connector. Existing ones are kept as staff left them."""
    definitions = {d.key: d for d in available_definitions()}
    ready = []
    for env_key in django_settings.INTEGRATIONS_PLATFORM_ACCOUNTS:
        definition = definitions.get(env_key)
        if definition is None:
            continue
        account = PlatformAccount.objects.filter(env_key=env_key).first()
        if account is None:
            # One made before accounts were keyed by .env entry adopts it.
            account = PlatformAccount.objects.filter(connector_key=env_key, env_key="").first()
            if account is None:
                account = PlatformAccount(
                    name=f"Telejects {definition.parsed.name}", connector_key=env_key
                )
            account.env_key = env_key
            account.save()
        if account.configured:
            ready.append(account)
    return ready


@transaction.atomic
def ensure_default_connections(realm: Realm) -> list[Connection]:
    """Give the company a connection, through Telejects' account, to every provider it may use
    and isn't connected to yet. Each is then tested and its products synced."""
    created = []
    for account in accounts_for(realm.id):
        connections = Connection.objects.in_realm(realm)
        if connections.filter(connector_key=account.connector_key).exists():
            continue
        definition = account.definition()
        base = definition.parsed.name if definition else account.connector_key
        name, n = base, 2
        while connections.filter(name__iexact=name).exists():
            name, n = f"{base} {n}", n + 1
        connection = Connection.objects.create(
            realm=realm,
            name=name,
            connector_key=account.connector_key,
            credentials=Connection.Source.PLATFORM,
            platform_account=account,
        )
        _schedule(connection, "connect", Trigger.CONNECT)
        created.append(connection)
    if created:
        events.publish(realm.id, TOPIC)
    return created


def ensure_everywhere() -> int:
    """Telejects' accounts from .env, and every company connected to them. Safe to re-run: run by
    `make migrate` (load_connectors) and the hourly integrations job."""
    ensure_platform_accounts()
    return sum(len(ensure_default_connections(realm)) for realm in Realm.objects.order_by("id"))


# --- grants (platform staff only: Django admin and manage.py) ----------------------------------


@transaction.atomic
def grant_platform_account(realm: Realm, account: PlatformAccount) -> PlatformGrant:
    """Let a company use a platform account. It is connected through it straight away, unless
    it already has a connection to that provider, which keeps its own account."""
    grant, _ = PlatformGrant.objects.in_realm(realm).get_or_create(realm=realm, account=account)
    existing = Connection.objects.in_realm(realm).filter(connector_key=account.connector_key)
    if not existing.exists():
        definition = account.definition()
        base = definition.parsed.name if definition else account.connector_key
        name, n = f"{base} (Telejects account)", 2
        while Connection.objects.in_realm(realm).filter(name__iexact=name).exists():
            name, n = f"{base} (Telejects account {n})", n + 1
        connection = Connection.objects.create(
            realm=realm,
            name=name,
            connector_key=account.connector_key,
            credentials=Connection.Source.PLATFORM,
            platform_account=account,
        )
        _schedule(connection, "connect", Trigger.CONNECT)
    else:
        # A connection the grant was withdrawn from earlier comes back on.
        back = existing.filter(platform_account=account, enabled=False)
        for connection in back:
            connection.enabled = True
            connection.save(update_fields=["enabled", "updated_at"])
            _schedule(connection, "connect", Trigger.CONNECT)
    events.publish(realm.id, TOPIC)
    return grant


@transaction.atomic
def withdraw_platform_account(realm: Realm, account: PlatformAccount) -> int:
    """Stop a company using a platform account. Its connections through it are turned off;
    their runs and results stay. Returns how many were turned off."""
    PlatformGrant.objects.in_realm(realm).of_account(account).delete()
    using = Connection.objects.in_realm(realm).filter(platform_account=account, enabled=True)
    count = using.update(enabled=False, updated_at=timezone.now())
    events.publish(realm.id, TOPIC)
    return count


@transaction.atomic
def remove_connection(connection: Connection) -> bool:
    """Delete it, or only disable it when runs used it (their results must stay readable).
    Returns whether it was deleted."""
    realm_id = connection.realm_id
    try:
        with transaction.atomic():
            ProviderProduct.objects.in_realm(realm_id).filter(connection=connection).delete()
            connection.delete()
        deleted = True
    except ProtectedError, RestrictedError:
        connection.enabled = False
        connection.save(update_fields=["enabled", "updated_at"])
        deleted = False
    events.publish(realm_id, TOPIC)
    return deleted


def request_operation(connection: Connection, operation: str) -> None:
    """Test or sync now, from the portal."""
    if not connection.enabled:
        raise ValidationError({"detail": "Turn the connection on first."})
    _schedule(connection, operation, Trigger.MANUAL)


# --- operations (run by the worker) -----------------------------------------------------------


def _start(connection: Connection, kind: str, trigger: str) -> SyncRun:
    run = SyncRun.objects.create(
        realm_id=connection.realm_id,
        connection=connection,
        kind=kind,
        trigger=trigger,
        **usage_of(connection),
    )
    events.publish(connection.realm_id, TOPIC)
    return run


def _finish(run: SyncRun, error: ConnectorError | None = None) -> None:
    run.finished_at = timezone.now()
    run.outcome = SyncRun.Outcome.FAILED if error else SyncRun.Outcome.OK
    if error:
        run.error_kind = error.kind
        run.error = error.message[:500]
    run.save()
    events.publish(run.realm_id, TOPIC)


def _set_health(owner: Connection | PlatformAccount, error: ConnectorError | None) -> None:
    """Record what a check said about the credentials it used: a company's own connection's,
    or a platform account's (shared by every company using it)."""
    owner.health_checked_at = timezone.now()
    if error is None:
        owner.health, owner.health_error = Health.OK, ""
    elif error.kind == ErrorKind.AUTH:
        owner.health, owner.health_error = Health.FAILING, error.message[:500]
    else:
        # Not the credentials' fault: say so, but keep what we last knew about them.
        owner.health_error = error.message[:500]
    owner.save(update_fields=["health", "health_error", "health_checked_at", "updated_at"])
    if isinstance(owner, PlatformAccount):
        _publish_platform(owner)


def _health_owner(connection: Connection) -> Connection | PlatformAccount:
    account = granted_account(connection)
    return account if account is not None else connection


def _publish_platform(account: PlatformAccount) -> None:
    """Tell every company using a platform account that its connections changed."""
    realms = (
        Connection.objects.across_realms()
        .filter(platform_account=account)
        .values_list("realm_id", flat=True)
        .distinct()
    )
    for realm_id in realms:
        events.publish(realm_id, TOPIC)


def mark_credentials_refused(connection: Connection, error: ConnectorError) -> None:
    """A run's provider call was refused: those credentials are failing until they're fixed."""
    _set_health(_health_owner(connection), error)
    events.publish(connection.realm_id, TOPIC)


def test_connection(connection: Connection, trigger: str) -> bool:
    run = _start(connection, Kind.TEST_CONNECTION, trigger)
    error = None
    try:
        recorder = recorder_for(connection, Kind.TEST_CONNECTION, sync_id=run.id)
        connector, definition = connector_for(connection, recorder)
        run.definition_version = definition.version
        connector.test_connection()
    except ConnectorError as failure:
        error = failure
    _set_health(_health_owner(connection), error)
    _finish(run, error)
    return error is None


def sync_products(connection: Connection, trigger: str) -> bool:
    run = _start(connection, Kind.SYNC_PRODUCTS, trigger)
    try:
        recorder = recorder_for(connection, Kind.SYNC_PRODUCTS, sync_id=run.id)
        connector, definition = connector_for(connection, recorder)
        run.definition_version = definition.version
        found, _calls = connector.list_products()
    except ConnectorError as error:
        if error.kind == ErrorKind.AUTH:
            _set_health(_health_owner(connection), error)
        _finish(run, error)
        return False
    if not found:
        _finish(run, ConnectorError(ErrorKind.BAD_RESPONSE, "The provider listed no products."))
        return False
    _apply_catalogue(connection, run, found)
    _finish(run)
    return True


@transaction.atomic
def _apply_catalogue(connection: Connection, run: SyncRun, found) -> None:
    products = ProviderProduct.objects.in_realm(connection.realm_id).filter(connection=connection)
    existing = {p.code: p for p in products}
    now = timezone.now()
    for info in found:
        product = existing.pop(info.code, None)
        if product is None:
            ProviderProduct.objects.create(
                realm_id=connection.realm_id,
                connection=connection,
                code=info.code,
                name=info.name[:255],
                product_type=info.product_type,
                raw=info.raw,
            )
            run.added += 1
            continue
        product.name = info.name[:255]
        product.product_type = info.product_type
        product.raw = info.raw
        if product.retired_at is not None:
            product.retired_at = None
            run.added += 1
        product.save()
    for product in existing.values():
        if product.retired_at is None:
            product.retired_at = now
            product.save(update_fields=["retired_at"])
            run.retired += 1


def run_operation(realm_id: int, connection_id: int, operation: str, trigger: str) -> None:
    """The worker's entry point. "connect" tests first and only syncs when that worked."""
    connection = Connection.objects.in_realm_id(realm_id).by_id(connection_id)
    if connection is None or not connection.enabled:
        return
    if operation == "connect":
        if test_connection(connection, trigger):
            sync_products(connection, trigger)
    elif operation == Kind.TEST_CONNECTION:
        test_connection(connection, trigger)
    elif operation == Kind.SYNC_PRODUCTS:
        sync_products(connection, trigger)
    else:
        raise ValueError(f"Unknown operation {operation!r}")


def due_operations(now=None) -> list[tuple[int, int, str]]:
    """(realm id, connection id, operation) for every scheduled operation that is due, in every
    company. Each is then run with its own company's id."""
    now = now or timezone.now()
    definitions = {d.key: d.parsed for d in ConnectorDefinition.objects.latest()}
    due = []
    for connection in Connection.objects.across_realms().enabled().order_by("id"):
        spec = definitions.get(connection.connector_key)
        if spec is None:
            continue
        for schedule in spec.schedules:
            # A platform account's credentials are checked once, not once per company.
            if connection.uses_platform and schedule.operation == Kind.TEST_CONNECTION:
                continue
            last = SyncRun.objects.in_realm_id(connection.realm_id).last_of(
                connection, schedule.operation
            )
            if last is None or last.started_at <= now - timedelta(hours=schedule.every_hours):
                due.append((connection.realm_id, connection.id, schedule.operation))
    return due


# --- platform accounts (run by the worker) ------------------------------------------------------


def test_platform_account(account_id: int) -> bool:
    """Check a platform account's credentials once, for every company using it."""
    account = PlatformAccount.objects.filter(pk=account_id, enabled=True).first()
    if account is None:
        return False
    definition = account.definition()
    error = None
    try:
        if definition is None:
            raise ConnectorError(ErrorKind.BAD_REQUEST, "Its connector is no longer offered.")
        build_connector(definition.parsed, account.settings, account.secrets).test_connection()
    except ConnectorError as failure:
        error = failure
    _set_health(account, error)
    return error is None


def due_platform_checks(now=None) -> list[int]:
    """Platform accounts whose scheduled credential check is due."""
    now = now or timezone.now()
    definitions = {d.key: d.parsed for d in ConnectorDefinition.objects.latest()}
    due = []
    for account in PlatformAccount.objects.enabled().order_by("id"):
        if not account.configured:
            continue
        spec = definitions.get(account.connector_key)
        hours = next(
            (
                s.every_hours
                for s in (spec.schedules if spec else [])
                if s.operation == "test_connection"
            ),
            None,
        )
        if hours is None:
            continue
        checked = account.health_checked_at
        if checked is None or checked <= now - timedelta(hours=hours):
            due.append(account.id)
    return due
