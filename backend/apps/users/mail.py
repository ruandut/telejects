"""The invitation email.

`enqueue_invitation` hands the work to Hatchet; `deliver_invitation` is what the task runs. The
token is created here, at sending time, and only its hash is saved: it never passes through the
queue or the database in the clear.
"""

import secrets

from django.conf import settings
from django.core.mail import send_mail

from apps.realms.models import RealmMembership

from .models import Invitation
from .services import hash_token


def enqueue_invitation(realm_id: int, invitation_id: int) -> None:
    # Imported here: tasks.py builds the Hatchet client, which needs a token to exist.
    from .tasks import InvitationInput, send_invitation_email

    send_invitation_email.run_no_wait(
        InvitationInput(realm_id=realm_id, invitation_id=invitation_id)
    )


def deliver_invitation(realm_id: int, invitation_id: int) -> bool:
    """Send the email for this invitation. False when it's gone or no longer wanted."""
    invitation = Invitation.objects.in_realm_id(realm_id).unsent(invitation_id).first()
    if invitation is None or invitation.membership.status != RealmMembership.Status.INVITED:
        return False

    token = secrets.token_urlsafe(32)
    invitation.token_hash = hash_token(token)
    invitation.save(update_fields=["token_hash"])

    membership = invitation.membership
    company = membership.realm.name
    greeting = f"Hello {membership.name}," if membership.name else "Hello,"
    link = f"{settings.APP_URL}/accept-invite?token={token}"
    send_mail(
        f"Confirm your account for {company}",
        f"{greeting}\n\n"
        f"You've been added to {company} on Telejects.\n\n"
        f"Confirm your account here:\n{link}\n\n"
        "The link works once and expires in 7 days. If you weren't expecting this, "
        "you can ignore this email.\n",
        settings.DEFAULT_FROM_EMAIL,
        [membership.user.email],
    )
    return True
