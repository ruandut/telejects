"""Integration workflows: testing and syncing a connection, and the hourly look for what's due."""

from datetime import timedelta

from django.db import close_old_connections
from hatchet_sdk import Context, EmptyModel
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


class OperationInput(BaseModel):
    realm_id: int
    connection_id: int
    operation: str  # "connect", "test_connection" or "sync_products"
    trigger: str


@hatchet.task(
    name="integrations-run-operation",
    input_validator=OperationInput,
    execution_timeout=timedelta(minutes=5),
    retries=1,
)
def run_connection_operation(input: OperationInput, ctx: Context) -> dict:
    from .services import run_operation

    close_old_connections()
    try:
        run_operation(input.realm_id, input.connection_id, input.operation, input.trigger)
        return {"done": True}
    finally:
        close_old_connections()


class PlatformAccountInput(BaseModel):
    """Platform data, not a company's: a platform account's own credential check (0004)."""

    account_id: int


@hatchet.task(
    name="integrations-test-platform-account",
    input_validator=PlatformAccountInput,
    execution_timeout=timedelta(minutes=5),
    retries=1,
)
def test_platform_account(input: PlatformAccountInput, ctx: Context) -> dict:
    from .services import test_platform_account as run_test

    close_old_connections()
    try:
        return {"ok": run_test(input.account_id)}
    finally:
        close_old_connections()


@hatchet.task(name="integrations-due", on_crons=["7 * * * *"])
def integrations_due(input: EmptyModel, ctx: Context) -> dict:
    """Start every scheduled sync and check that is due, each in its own company, and the
    credential checks of Telejects' platform accounts, once each."""
    from .services import due_operations, due_platform_checks

    close_old_connections()
    try:
        due = due_operations()
        accounts = due_platform_checks()
    finally:
        close_old_connections()
    for account_id in accounts:
        test_platform_account.run_no_wait(PlatformAccountInput(account_id=account_id))
    if due:
        run_connection_operation.run_many(
            [
                run_connection_operation.create_bulk_run_item(
                    input=OperationInput(
                        realm_id=realm_id,
                        connection_id=connection_id,
                        operation=operation,
                        trigger="scheduled",
                    )
                )
                for realm_id, connection_id, operation in due
            ],
            wait_for_result=False,
        )
    return {"started": len(due), "platform_checks": len(accounts)}


TASKS = [run_connection_operation, test_platform_account, integrations_due]
