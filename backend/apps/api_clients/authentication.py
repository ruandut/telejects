"""Signing a request in with an API client's OAuth2 token.

Only endpoints that opt in list `ApiClientAuthentication`; everything else stays JWT only, so
a client token never reaches a person's own endpoints (`me`, changing a password).

The request's user is an `ApiClientUser`. `InRealm` sees its `client_membership` and works in
the client's company: no X-Realm is needed, and one naming another company is refused.
"""

from django.utils import timezone
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.exceptions import AuthenticationFailed

from apps.realms.access_control import PERMISSIONS
from apps.realms.models import RealmMembership

from .models import ApiClient

USED_EVERY_SECONDS = 60


class ClientMembership:
    """Stands in for a membership on an API client's requests. It may do what its client was
    given, and only while its maker is still an active member who may do it too."""

    def __init__(self, client: ApiClient, maker: RealmMembership):
        self.client = client
        self.maker = maker
        self.realm = client.realm
        self.realm_id = client.realm_id
        self.user = None

    @property
    def is_active(self) -> bool:
        return self.client.is_active and self.maker.is_active

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset(self.client.permissions) & self.maker.permissions

    def has_perm(self, code: str, project=None) -> bool:
        if code not in PERMISSIONS:
            raise KeyError(f"Unknown permission {code!r}; add it to access_control.PERMISSIONS")
        return self.is_active and code in self.permissions


class ApiClientUser:
    """`request.user` on an API client's requests. Not a person: it has no id or email."""

    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_staff = False
    is_superuser = False
    pk = id = None

    def __init__(self, client: ApiClient, membership: ClientMembership):
        self.api_client = client
        self.client_membership = membership

    def __str__(self):
        return f"API client {self.api_client.name}"


class ApiClientAuthentication(OAuth2Authentication):
    def authenticate(self, request):
        found = super().authenticate(request)
        if found is None:
            return None  # not one of ours: JWT authentication gets its turn
        _, token = found
        client = ApiClient.objects.for_token(token.application_id)
        if client is None:
            raise AuthenticationFailed("This API client has been revoked.")
        maker = (
            RealmMembership.objects.in_realm(client.realm_id)
            .active()
            .filter(user_id=client.created_by_id)
            .select_related("role")
            .first()
        )
        if maker is None:
            raise AuthenticationFailed("This API client's maker is no longer in the company.")
        now = timezone.now()
        if (
            client.last_used_at is None
            or (now - client.last_used_at).total_seconds() > USED_EVERY_SECONDS
        ):
            ApiClient.objects.in_realm(client.realm_id).filter(pk=client.pk).update(
                last_used_at=now
            )
        return ApiClientUser(client, ClientMembership(client, maker)), token

    def authenticate_header(self, request):
        return 'Bearer realm="api"'
