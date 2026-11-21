"""Automation timers: every minute, fire the dates that arrived, the schedules that are due and
the actions whose wait is over."""

from django.db import close_old_connections
from hatchet_sdk import Context, EmptyModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


@hatchet.task(name="automations-tick", on_crons=["* * * * *"])
def automations_tick(input: EmptyModel, ctx: Context) -> dict:
    from .services import tick

    close_old_connections()
    try:
        return tick()
    finally:
        close_old_connections()


TASKS = [automations_tick]
