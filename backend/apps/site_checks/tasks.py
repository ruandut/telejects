"""One-site checks on Hatchet: one task per provider call.

Someone is waiting on these, so they run ahead of bulk work (priority 3), under the same
per-credentials limits as bulk checks: everyone on one of Telejects' accounts shares them.
"""

from datetime import timedelta

from django.db import close_old_connections
from hatchet_sdk import ConcurrencyExpression, ConcurrencyLimitStrategy, Context
from hatchet_sdk.rate_limit import RateLimit, RateLimitDuration
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


class CallInput(BaseModel):
    realm_id: int
    call_id: int
    limit_key: str
    max_concurrency: int
    requests_per_minute: int


@hatchet.task(
    name="site-check-call",
    input_validator=CallInput,
    execution_timeout=timedelta(minutes=2),
    default_priority=3,
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
def site_check_call(input: CallInput, ctx: Context) -> dict:
    from .services import perform_call

    close_old_connections()
    try:
        return {"status": perform_call(input.realm_id, input.call_id)}
    finally:
        close_old_connections()


def enqueue_calls(realm_id: int, call_ids: list[int]) -> None:
    from .services import runtime_for

    limits = runtime_for(realm_id, call_ids)
    items = [
        site_check_call.create_bulk_run_item(
            input=CallInput(
                realm_id=realm_id,
                call_id=call_id,
                limit_key=limit_key,
                max_concurrency=max_concurrency,
                requests_per_minute=requests_per_minute,
            )
        )
        for call_id, (limit_key, max_concurrency, requests_per_minute) in limits.items()
    ]
    if items:
        site_check_call.run_many(items, wait_for_result=False)


TASKS = [site_check_call]
