"""Presence: every minute, tabs that went quiet leave their boards."""

from django.db import close_old_connections
from hatchet_sdk import Context, EmptyModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


@hatchet.task(name="presence-sweep", on_crons=["* * * * *"])
def presence_sweep(input: EmptyModel, ctx: Context) -> dict:
    from .services import sweep

    close_old_connections()
    try:
        return {"removed": sweep()}
    finally:
        close_old_connections()


TASKS = [presence_sweep]
