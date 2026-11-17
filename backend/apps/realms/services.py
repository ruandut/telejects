"""Creating companies and their built-in roles. Changes to people (name, role, status) belong to
apps/users/services.py."""

from django.db import transaction

from .access_control import SYSTEM_ROLES
from .models import Realm, RealmMembership, Role


def ensure_system_roles(realm: Realm) -> dict[str, Role]:
    """Give the company every built-in role it lacks; returns them by key. Safe to re-run."""
    roles = {}
    for position, (key, spec) in enumerate(SYSTEM_ROLES.items()):
        role, _ = Role.objects.in_realm(realm).update_or_create(
            realm=realm,
            key=key,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "is_system": True,
                "position": position,
            },
        )
        roles[key] = role
    return roles


@transaction.atomic
def create_realm(name: str) -> Realm:
    """A new company with the built-in roles, and nobody in it yet."""
    realm = Realm.objects.create(name=name.strip())
    ensure_system_roles(realm)
    return realm


def add_member(realm: Realm, user, role_key: str, *, name: str = "") -> RealmMembership:
    """Put an existing account straight into the company as active. For setup and tests; the
    portal adds people by invitation (apps/users)."""
    role = Role.objects.in_realm(realm).by_key(role_key)
    membership, _ = RealmMembership.objects.in_realm(realm).get_or_create(
        realm=realm, user=user, defaults={"role": role, "name": name}
    )
    return membership
