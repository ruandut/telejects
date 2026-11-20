"""Writing to the integration log, and keeping each company within its limit.

`Recorder` is what a provider call reports its exchanges to: one per call site, carrying what
the entries belong to. It redacts once more (a platform connection's settings, header names that
carry credentials), caps bodies at 256 KB, writes each entry in its own transaction, and never
lets a logging failure break the provider call.
"""

import json
import logging
from dataclasses import dataclass, field

from django.apps import apps
from django.db import transaction

from apps.realms import events

from .models import IntegrationLog, LogRetention

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 256 * 1024
REDACTED = "[redacted]"
TOPIC = "integration_logs"
# Header names that carry credentials, whatever a definition calls them; compared lowercased.
SECRET_HEADERS = {
    "authorization",
    "x-api-key",
    "api-key",
    "apikey",
    "proxy-authorization",
    "cookie",
}


def default_limit() -> int:
    return apps.get_app_config("integration_logs").default_limit


def limit_for(realm_id: int) -> int:
    retention = LogRetention.objects.in_realm_id(realm_id).first()
    return retention.max_entries if retention else default_limit()


def set_limit(realm_id: int, max_entries: int) -> None:
    """Staff only (Django admin). Lowering it removes the oldest entries at once."""
    LogRetention.objects.in_realm_id(realm_id).update_or_create(
        realm_id=realm_id, defaults={"max_entries": max_entries}
    )
    prune(realm_id)


def prune(realm_id: int) -> int:
    """Delete the company's entries beyond its limit, oldest first."""
    limit = limit_for(realm_id)
    entries = IntegrationLog.objects.in_realm_id(realm_id)
    cutoff = entries.newest().values_list("id", flat=True)[limit : limit + 1]
    cutoff = list(cutoff)
    if not cutoff:
        return 0
    deleted, _ = entries.filter(id__lte=cutoff[0]).delete()
    return deleted


def _text(value) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
    raw = text.encode()
    if len(raw) <= MAX_BODY_BYTES:
        return text
    cut = raw[:MAX_BODY_BYTES].decode(errors="ignore")
    return f"{cut}\n… truncated ({len(raw) // 1024} KB in all)"


def _headers(headers: dict, extra_secret_names: set[str]) -> dict:
    hidden = SECRET_HEADERS | {n.lower() for n in extra_secret_names}
    return {k: (REDACTED if k.lower() in hidden else v) for k, v in (headers or {}).items()}


class _Redact:
    def __init__(self, values):
        self.values = sorted(
            {str(v) for v in values if v not in (None, "") and len(str(v)) > 2},
            key=len,
            reverse=True,
        )

    def __call__(self, data):
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


@dataclass
class Recorder:
    """Collects a provider call's exchanges into the log (see module doc)."""

    realm_id: int
    operation: str
    connection_id: int | None = None
    connection_name: str = ""
    connector_key: str = ""
    credentials: str = ""
    definition_version: int | None = None
    run_id: int | None = None
    check_id: int | None = None
    sync_id: int | None = None
    site_check_id: int | None = None
    attempt: int = 1
    # Values to hide beyond the engine's own redaction (a platform account's settings).
    hide: list = field(default_factory=list)
    secret_header_names: set = field(default_factory=set)
    written: list = field(default_factory=list)

    def __call__(self, exchange) -> None:
        try:
            self._write(exchange)
        except Exception:
            logger.exception("Couldn't write an integration log entry")

    def _write(self, exchange) -> None:
        redact = _Redact(self.hide)
        request = redact(exchange.request or {})
        entry = IntegrationLog(
            realm_id=self.realm_id,
            operation=self.operation,
            connection_id=self.connection_id,
            connection_name=self.connection_name[:100],
            connector_key=self.connector_key,
            credentials=self.credentials,
            definition_version=self.definition_version,
            run_id=self.run_id,
            check_id=self.check_id,
            sync_id=self.sync_id,
            site_check_id=self.site_check_id,
            attempt=self.attempt,
            method=str(request.get("method", ""))[:10],
            url=_text(request.get("url", "")),
            request_headers=_headers(request.get("headers") or {}, self.secret_header_names),
            request_body=_text(request.get("body")),
            status_code=exchange.status_code,
            response_headers=_headers(redact(exchange.response_headers or {}), set()),
            response_body=_text(redact(exchange.response)),
            duration_ms=exchange.duration_ms,
            outcome=exchange.error_kind or "ok",
            error=redact(exchange.error or "")[:500],
        )
        if query := request.get("query"):
            entry.url = _text(f"{entry.url}?{'&'.join(f'{k}={v}' for k, v in query.items())}")
        with transaction.atomic():
            entry.save()
            prune(self.realm_id)
            events.publish(self.realm_id, TOPIC, items=[entry.id])
        self.written.append(entry.id)
