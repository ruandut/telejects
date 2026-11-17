"""Platform tasks. Domain apps keep their own in apps/<app>/tasks.py."""

from django.db import close_old_connections, connection
from hatchet_sdk import Context, EmptyModel

from .hatchet import get_hatchet

hatchet = get_hatchet()


@hatchet.task(name="ping")
def ping(input: EmptyModel, ctx: Context) -> dict:
    """Proves the worker is connected and can reach the database."""
    close_old_connections()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"postgres": "ok"}
    finally:
        close_old_connections()


TASKS = [ping]
