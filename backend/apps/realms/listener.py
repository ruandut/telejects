"""One background task per API process: LISTEN on Postgres and hand each event to the websocket
group of its company. Started by the first websocket that connects; reconnects if the database
connection drops."""

import asyncio
import json
import logging

import psycopg
from channels.layers import get_channel_layer
from django.db import connection

from .events import PG_CHANNEL, group_name

logger = logging.getLogger(__name__)

RETRY_SECONDS = 2
_task: asyncio.Task | None = None


def ensure_listening() -> asyncio.Task:
    global _task
    loop = asyncio.get_running_loop()
    if _task is None or _task.done() or _task.get_loop() is not loop:
        _task = loop.create_task(_listen_forever())
    return _task


async def _listen_forever() -> None:
    while True:
        try:
            await _listen()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Lost the event listener's database connection; reconnecting")
        await asyncio.sleep(RETRY_SECONDS)


def parse(payload: str) -> dict | None:
    try:
        event = json.loads(payload)
        items = event.get("items")
        return {
            "realm": int(event["realm"]),
            "topic": str(event["topic"]),
            "subject": None if event.get("subject") is None else int(event["subject"]),
            "items": None if items is None else [int(i) for i in items],
            "has_items": "items" in event,
        }
    except ValueError, KeyError, TypeError, AttributeError:
        return None


async def _listen() -> None:
    layer = get_channel_layer()
    # The same database Django uses, on a connection of its own.
    params = connection.get_connection_params()
    params.pop("cursor_factory", None)
    params.pop("context", None)
    async with await psycopg.AsyncConnection.connect(**params, autocommit=True) as listening:
        await listening.execute(f"LISTEN {PG_CHANNEL}")
        async for notice in listening.notifies():
            event = parse(notice.payload)
            if event is None:
                logger.warning("Ignored a malformed event")
                continue
            await layer.group_send(group_name(event["realm"]), {"type": "realm.event", **event})
