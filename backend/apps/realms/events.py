"""Telling a company's open browser tabs that something changed, from any process.

`publish` is called by services, in the API or in the Hatchet worker. It sends a Postgres NOTIFY,
which Postgres delivers when the surrounding transaction commits, and never if it rolls back.
Every API process LISTENs (listener.py) and hands the event to that company's websockets
(consumers.py), which decide per subscriber what, if anything, to send.

An event carries ids only: the topic, optionally the id of the thing it is about (a run) and the
ids of the rows that changed. NOTIFY payloads are capped at 8 KB and nobody checks access on
them, so the data itself is always loaded by the consumer, through the owning app's scoped
queryset and serializer (live.py).
"""

import json

from django.db import connection

PG_CHANNEL = "telejects_events"
# More changed rows than this and the event says "everything may have changed" instead.
MAX_ITEMS = 400


def group_name(realm_id: int) -> str:
    return f"realm-{realm_id}"


def publish(realm_id: int, topic: str, subject: int | None = None, items=None) -> None:
    payload = {"realm": realm_id, "topic": topic, "subject": subject}
    if items is not None:
        items = sorted({int(i) for i in items})
        payload["items"] = items if len(items) <= MAX_ITEMS else None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, %s)", [PG_CHANNEL, json.dumps(payload)])
