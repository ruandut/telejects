"""Feasibility runs on Hatchet: planning a run into provider checks, then one task per check.

Each check task is limited per connection (its connector's concurrency and requests per minute),
so a big run never floods a provider, and runs in its own company (realm_id). Companies using
one of Telejects' platform accounts share that account's limits.
"""

from datetime import timedelta

from django.db import close_old_connections
from hatchet_sdk import ConcurrencyExpression, ConcurrencyLimitStrategy, Context
from hatchet_sdk.rate_limit import RateLimit, RateLimitDuration
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


class RunInput(BaseModel):
    realm_id: int
    run_id: int


class CheckInput(BaseModel):
    realm_id: int
    run_id: int
    check_id: int
    # Whose credentials the call uses: "connection-<id>" or, shared by every company on one of
    # Telejects' accounts, "platform-<id>" (0004).
    limit_key: str
    max_concurrency: int
    requests_per_minute: int


@hatchet.task(
    name="feasibility-check",
    input_validator=CheckInput,
    execution_timeout=timedelta(minutes=10),
    retries=1,
    concurrency=ConcurrencyExpression(
        expression="input.limit_key",
        max_runs="input.max_concurrency",
        limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
    ),
    rate_limits=[
        RateLimit(
            dynamic_key="input.limit_key",
            units=1,
            limit="input.requests_per_minute",
            duration=RateLimitDuration.MINUTE,
        )
    ],
)
def feasibility_check(input: CheckInput, ctx: Context) -> dict:
    from .services import perform_check

    close_old_connections()
    try:
        return {"status": perform_check(input.realm_id, input.check_id)}
    finally:
        close_old_connections()


def enqueue_checks(realm_id: int, run_id: int, check_ids: list[int]) -> None:
    from .services import runtime_for

    if not check_ids:
        return
    limits = runtime_for(realm_id, check_ids)
    items = [
        feasibility_check.create_bulk_run_item(
            input=CheckInput(
                realm_id=realm_id,
                run_id=run_id,
                check_id=check_id,
                limit_key=limit_key,
                max_concurrency=max_concurrency,
                requests_per_minute=requests_per_minute,
            )
        )
        for check_id, (limit_key, max_concurrency, requests_per_minute) in limits.items()
    ]
    for start in range(0, len(items), 500):
        feasibility_check.run_many(items[start : start + 500], wait_for_result=False)


@hatchet.task(
    name="feasibility-plan-run",
    input_validator=RunInput,
    execution_timeout=timedelta(minutes=5),
    retries=1,
)
def plan_feasibility_run(input: RunInput, ctx: Context) -> dict:
    from .services import plan_run

    close_old_connections()
    try:
        check_ids = plan_run(input.realm_id, input.run_id)
        enqueue_checks(input.realm_id, input.run_id, check_ids)
        return {"checks": len(check_ids)}
    finally:
        close_old_connections()


TASKS = [plan_feasibility_run, feasibility_check]
