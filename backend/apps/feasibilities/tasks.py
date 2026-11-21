"""Feasibility runs on Hatchet: planning a run into provider checks, then one task per check.

Each check task is limited per connection (its connector's concurrency and requests per minute),
so a big run never floods a provider, and runs in its own company (realm_id). Companies using
one of Telejects' platform accounts share that account's limits, and take turns within them:
a busy company slows the others down but never holds them up.
"""

from datetime import datetime, timedelta

from django.db import close_old_connections
from hatchet_sdk import ConcurrencyExpression, ConcurrencyLimitStrategy, Context, V1TaskStatus
from hatchet_sdk.rate_limit import RateLimit, RateLimitDuration
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()

FAIR_KEY = 'input.limit_key + ":" + string(input.realm_id)'


class RunInput(BaseModel):
    realm_id: int
    run_id: int


class DropInput(BaseModel):
    realm_id: int
    run_id: int
    since: datetime
    until: datetime


def run_tag(realm_id: int, run_id: int) -> dict[str, str]:
    """The metadata every check task of a run carries, so its queued tasks can be dropped."""
    return {"feasibility_run": f"{realm_id}:{run_id}"}


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
    concurrency=[
        # The provider's limit for the account, whoever is using it.
        ConcurrencyExpression(
            expression="input.limit_key",
            max_runs="input.max_concurrency",
            limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
        ),
        # Turns between companies on one account, so each sees progress. A company's own runs
        # stay first come, first served (pause one to let another go first).
        ConcurrencyExpression(
            expression=FAIR_KEY,
            max_runs="input.max_concurrency",
            limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
        ),
    ],
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
            additional_metadata=run_tag(realm_id, run_id),
            input=CheckInput(
                realm_id=realm_id,
                run_id=run_id,
                check_id=check_id,
                limit_key=limit_key,
                max_concurrency=max_concurrency,
                requests_per_minute=requests_per_minute,
            ),
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


@hatchet.task(
    name="feasibility-drop-queued",
    input_validator=DropInput,
    execution_timeout=timedelta(minutes=10),
    retries=1,
)
def drop_queued_checks(input: DropInput, ctx: Context) -> dict:
    """Cancel, in Hatchet, a paused or cancelled run's check tasks that haven't started. They
    would only skip, but each would still take a turn and a unit of the provider's rate limit
    from everyone on that account. Only tasks queued before the pause go (`until`), so a run
    continued meanwhile keeps its new ones. Calls already under way finish."""
    hatchet.runs.bulk_cancel_by_filters_with_pagination(
        since=input.since,
        until=input.until,
        statuses=[V1TaskStatus.QUEUED],
        additional_metadata=run_tag(input.realm_id, input.run_id),
        sleep_time=1,
    )
    return {}


def enqueue_drop(realm_id: int, run_id: int, since: datetime, until: datetime) -> None:
    drop_queued_checks.run_no_wait(
        DropInput(realm_id=realm_id, run_id=run_id, since=since, until=until)
    )


TASKS = [plan_feasibility_run, feasibility_check, drop_queued_checks]
