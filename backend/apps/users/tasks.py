from django.db import close_old_connections
from hatchet_sdk import Context
from pydantic import BaseModel

from apps.jobs.hatchet import get_hatchet

hatchet = get_hatchet()


class InvitationInput(BaseModel):
    realm_id: int
    invitation_id: int


@hatchet.task(name="send-invitation-email", input_validator=InvitationInput, retries=3)
def send_invitation_email(input: InvitationInput, ctx: Context) -> dict:
    from .mail import deliver_invitation

    close_old_connections()
    try:
        return {"sent": deliver_invitation(input.realm_id, input.invitation_id)}
    finally:
        close_old_connections()


TASKS = [send_invitation_email]
