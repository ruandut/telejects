"""The "your password was changed" email (0002).

`enqueue_password_changed` hands the work to Hatchet; `deliver_password_changed` is what the task
runs. The email never contains a password.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail


def enqueue_password_changed(user_id: int) -> None:
    # Imported here: tasks.py builds the Hatchet client, which needs a token to exist.
    from .tasks import PasswordChangedInput, send_password_changed_email

    send_password_changed_email.run_no_wait(PasswordChangedInput(user_id=user_id))


def deliver_password_changed(user_id: int) -> bool:
    """Tell the person their password changed. False when the account is gone."""
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return False
    send_mail(
        "Your Telejects password was changed",
        "Hello,\n\n"
        f"The password for {user.email} on Telejects was just changed, "
        "and any other browsers you were signed in on have been signed out.\n\n"
        "If that was you, there's nothing more to do. If it wasn't, tell one of your "
        "company's Admins straight away.\n",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    return True
