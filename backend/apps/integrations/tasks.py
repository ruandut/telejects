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


@hatchet.task(name="integrations-due", on_crons=["7 * * * *"])
def integrations_due(input: EmptyModel, ctx: Context) -> dict:
    """Start every scheduled sync and check that is due, each in its own company."""
    from .services import due_operations

    close_old_connections()
    try:
        due = due_operations()
    finally:
        close_old_connections()
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
    return {"started": len(due)}


TASKS = [run_connection_operation, integrations_due]
