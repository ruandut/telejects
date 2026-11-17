"""Changes a person makes to their own account (spec 0002). Views only translate HTTP to these."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .mail import enqueue_password_changed


def _after_commit(func) -> None:
    """Run once the surrounding transaction commits. A seam the tests replace."""
    transaction.on_commit(func)


@transaction.atomic
def change_password(user, current: str, new: str) -> None:
    """Set `user`'s password to `new`, if `current` is the one they have now.

    Every token issued before stops working (SimpleJWT's CHECK_REVOKE_TOKEN: they carry a hash
    of the password), so other browsers are signed out. The person is told by email.
    """
    if not user.check_password(current):
        raise ValidationError({"current_password": ["That isn't your current password."]})
    if current == new:
        raise ValidationError({"new_password": ["Choose a password you aren't using now."]})
    try:
        validate_password(new, user)
    except DjangoValidationError as error:
        raise ValidationError({"new_password": list(error.messages)}) from error
    user.set_password(new)
    user.save(update_fields=["password"])
    user_id = user.id
    _after_commit(lambda: enqueue_password_changed(user_id))
