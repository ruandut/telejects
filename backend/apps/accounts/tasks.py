from django.db import close_old_connections
from hatchet_sdk import Context
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


class PasswordChangedInput(BaseModel):
    user_id: int


@hatchet.task(name="send-password-changed-email", input_validator=PasswordChangedInput, retries=3)
def send_password_changed_email(input: PasswordChangedInput, ctx: Context) -> dict:
    from .mail import deliver_password_changed

    close_old_connections()
    try:
        return {"sent": deliver_password_changed(input.user_id)}
    finally:
        close_old_connections()


TASKS = [send_password_changed_email]
