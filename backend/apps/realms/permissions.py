"""Which company a request works in, the gate that keeps every endpoint inside it, and the
permission checks.

A browser tab names its company in the X-Realm header, so two tabs on different companies can't
write into each other's. Without the header the user's oldest company is used. Either way the
user must be an active member, or the request is refused.

`InRealm` is a default permission class (see settings), so a new endpoint is company-gated
unless it says otherwise. It sets `request.realm` and `request.membership`. Querysets still
have to be scoped: TenantQuerySet refuses to run unscoped, RealmScopedViewSet scopes viewsets,
and every endpoint has isolation tests.
"""

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

# Kept apart from access.py: DRF imports this from settings while loading its own views module.
from .access_control import PERMISSIONS
from .models import RealmMembership

REALM_HEADER = "X-Realm"


class RealmRequired(PermissionDenied):
    """403 with a machine-readable `code`, so the frontend can tell this apart from others."""

    def __init__(self, detail: str, code: str):
        super().__init__({"detail": detail, "code": code})


def resolve_membership(request) -> RealmMembership:
    asked = request.headers.get(REALM_HEADER)
    if asked:
        membership = RealmMembership.objects.of_user(request.user).in_realm(asked).first()
        if membership is None:
            # The same answer whether the company exists or not, so ids can't be probed.
            raise RealmRequired("You aren't a member of that company.", "not_member")
        return membership
    membership = RealmMembership.objects.default_for(request.user)
    if membership is None:
        raise RealmRequired("You aren't part of any company yet.", "no_realm")
    return membership


class InRealm(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        membership = resolve_membership(request)
        request.membership = membership
        request.realm = membership.realm
        return True


def HasRealmPermission(read: str, write: str | None = None):  # noqa: N802 (reads like a class)
    """A DRF permission class for use after InRealm.

    Safe methods need `read`; anything else needs `write` (or `read` when no `write` is given).
    `HasRealmPermission("users.view", write="users.manage")`.
    """
    for code in (read, write):
        if code is not None and code not in PERMISSIONS:
            raise KeyError(f"Unknown permission {code!r}; add it to access_control.PERMISSIONS")

    class _HasRealmPermission(permissions.BasePermission):
        message = "You don't have permission to do this."
        codes = (read, write or read)

        def has_permission(self, request, view):
            membership = getattr(request, "membership", None)
            if membership is None:
                return False
            code = read if request.method in permissions.SAFE_METHODS else (write or read)
            return membership.has_perm(code)

    _HasRealmPermission.__name__ = f"HasRealmPermission({read!r}, write={write!r})"
    return _HasRealmPermission
