"""Everything that changes a company's users. Views only translate HTTP to these calls.

Every function takes the company (or a membership already looked up inside it) and never reaches
outside it. This is the only place that changes a membership's name, role or status.
"""

import hashlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.realms.access_control import ADMIN
from apps.realms.models import Realm, RealmMembership, Role
from apps.realms.services import create_realm

from .models import Invitation

Status = RealmMembership.Status

INVITATION_LIFETIME = timedelta(days=7)

NEEDS_ADMIN = "A company needs at least one Admin."
CHOOSE_SUCCESSOR = "Choose who takes over as Admin."


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _after_commit(func) -> None:
    """Run once the surrounding transaction commits. A seam the tests replace."""
    transaction.on_commit(func)


def _send_invitation(invitation: Invitation) -> None:
    from .mail import enqueue_invitation

    realm_id, invitation_id = invitation.realm_id, invitation.id
    _after_commit(lambda: enqueue_invitation(realm_id, invitation_id))


def _check_role(realm: Realm, role: Role) -> None:
    """The serializers only offer this company's roles; this holds for any other caller too."""
    if role.realm_id != realm.id:
        raise ValidationError({"role": "Choose one of your company's roles."})


# --- adding ----------------------------------------------------------------------------------


def _new_invitation(membership: RealmMembership) -> Invitation:
    """Replace any earlier link with a fresh one and send it."""
    Invitation.objects.in_realm(membership.realm_id).for_membership(membership).delete()
    invitation = Invitation.objects.create(
        realm_id=membership.realm_id,
        membership=membership,
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    _send_invitation(invitation)
    return invitation


@transaction.atomic
def add_user(realm: Realm, *, email: str, name: str, role: Role) -> RealmMembership:
    """Add someone to the company as invited, with that role, and email them a link.

    Behaves the same whether or not the address already has an account in another company, so
    adding can't be used to find out who uses Telejects.
    """
    _check_role(realm, role)
    email = email.strip().lower()
    users = get_user_model().objects
    account = users.filter(email=email).first()
    if account is None:
        # No usable password until they confirm, so the account can't sign in.
        account = users.create_user(email=email, password=None)

    membership = RealmMembership.objects.in_realm(realm).filter(user=account).first()
    if membership is not None and membership.status != Status.REMOVED:
        raise ValidationError({"email": "They're already a user here."})
    if membership is None:
        membership = RealmMembership(realm=realm, user=account)
    # A removed user who is added again starts over as invited.
    membership.name = name.strip()
    membership.role = role
    membership.status = Status.INVITED
    membership.save()

    _new_invitation(membership)
    return membership


@transaction.atomic
def resend_invitation(membership: RealmMembership) -> None:
    if membership.status != Status.INVITED:
        raise ValidationError({"detail": "They have already confirmed their account."})
    _new_invitation(membership)


# --- editing ---------------------------------------------------------------------------------


def _is_last_admin(membership: RealmMembership) -> bool:
    if not (membership.is_active and membership.is_admin):
        return False
    admins = RealmMembership.objects.in_realm(membership.realm_id).active().admins()
    return not admins.exclude(pk=membership.pk).exists()


@transaction.atomic
def update_user(membership: RealmMembership, *, name=None, role=None) -> RealmMembership:
    if role is not None and role.pk != membership.role_id:
        _check_role(membership.realm, role)
        if not role.is_admin and _is_last_admin(membership):
            raise ValidationError({"role": NEEDS_ADMIN})
        membership.role = role
    if name is not None:
        membership.name = name.strip()
    membership.save(update_fields=["name", "role"])
    return membership


# --- removing --------------------------------------------------------------------------------


@transaction.atomic
def remove_user(membership: RealmMembership, new_admin_id=None) -> None:
    """End someone's access to the company, or cancel their invitation. The row is kept
    (status removed), so past work stays attributable.

    Removing the company's only Admin hands the role to `new_admin_id`, who must be another
    active user of the same company.
    """
    realm_id = membership.realm_id
    if membership.is_active:
        others = RealmMembership.objects.in_realm(realm_id).active().exclude(pk=membership.pk)
        if not others.exists():
            raise ValidationError(
                {"detail": "They're the only active user. A company can't be left empty."}
            )
        if _is_last_admin(membership):
            successor = others.by_id(new_admin_id) if new_admin_id else None
            if successor is None:
                raise ValidationError({"new_admin": CHOOSE_SUCCESSOR})
            successor.role = Role.objects.in_realm(realm_id).by_key(ADMIN)
            successor.save(update_fields=["role"])
    Invitation.objects.in_realm(realm_id).for_membership(membership).delete()
    membership.status = Status.REMOVED
    membership.save(update_fields=["status"])


# --- confirming ------------------------------------------------------------------------------


class InvitationProblem(Exception):
    """The link can't be used. `code` is not_found, used or expired."""

    MESSAGES = {
        "not_found": "This link is no longer valid. Ask your administrator for a new one.",
        "used": "This link has already been used.",
        "expired": "This link has expired. Ask your administrator for a new one.",
    }

    def __init__(self, code: str):
        super().__init__(self.MESSAGES[code])
        self.code = code


def invitation_for(token: str) -> Invitation:
    invitation = Invitation.objects.by_token_hash(hash_token(token)) if token else None
    if invitation is None or invitation.membership.status == Status.REMOVED:
        raise InvitationProblem("not_found")
    if invitation.used_at is not None:
        raise InvitationProblem("used")
    if invitation.expires_at <= timezone.now() or invitation.membership.status != Status.INVITED:
        raise InvitationProblem("expired")
    return invitation


@transaction.atomic
def accept_invitation(token: str, password: str | None = None):
    """Confirm the account behind a link. Returns (membership, is_new_account).

    A new account must set a password here. An account that already has one just confirms, and
    signs in the usual way: holding a link never stands in for a password that exists.
    """
    invitation = invitation_for(token)
    membership = invitation.membership
    user = membership.user
    is_new = not user.has_usable_password()
    if is_new:
        if not password:
            raise ValidationError({"password": "Choose a password."})
        try:
            validate_password(password, user)
        except DjangoValidationError as error:
            raise ValidationError({"password": list(error.messages)}) from error
        user.set_password(password)
        user.save(update_fields=["password"])
    membership.status = Status.ACTIVE
    membership.save(update_fields=["status"])
    invitation.used_at = timezone.now()
    invitation.save(update_fields=["used_at"])
    return membership, is_new


# --- companies (platform staff) --------------------------------------------------------------


@transaction.atomic
def create_company(name: str, admin_email: str, admin_name: str = "") -> RealmMembership:
    """A new company, with its first Admin invited by email."""
    realm = create_realm(name)
    admin = Role.objects.in_realm(realm).by_key(ADMIN)
    return add_user(realm, email=admin_email, name=admin_name, role=admin)
