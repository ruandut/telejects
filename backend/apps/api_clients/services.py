"""Making and revoking API clients. Views only call these."""

import secrets

from django.db import transaction
from django.utils import timezone
from oauth2_provider.models import get_application_model
from rest_framework.exceptions import ValidationError

from apps.realms.models import RealmMembership

from .models import ApiClient

Application = get_application_model()

# What a client can be given: what the endpoints that take client tokens check (pricebook's
# Rapid endpoints). More join as the public API grows.
CLIENT_PERMISSIONS = ["feasibilities.run", "feasibilities.quote"]


@transaction.atomic
def create_client(maker: RealmMembership, *, name: str, permissions: list[str]) -> tuple:
    """A new client of the maker's company with some of the maker's own permissions.

    Returns (client, secret). The secret is stored hashed and can't be shown again."""
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Give the client a name."})
    if ApiClient.objects.in_realm(maker.realm_id).active().filter(name__iexact=name).exists():
        raise ValidationError({"name": "Another API client already has this name."})
    wanted = list(dict.fromkeys(permissions))
    unknown = [code for code in wanted if code not in CLIENT_PERMISSIONS]
    if unknown:
        raise ValidationError(
            {"permissions": f"An API client can't be given: {', '.join(unknown)}."}
        )
    beyond = [code for code in wanted if not maker.has_perm(code)]
    if beyond:
        raise ValidationError(
            {"permissions": f"You can't give permissions you don't have: {', '.join(beyond)}."}
        )
    if not wanted:
        raise ValidationError({"permissions": "Choose at least one permission."})
    secret = secrets.token_urlsafe(40)
    application = Application.objects.create(
        name=f"realm-{maker.realm_id}: {name}"[:255],
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
        client_secret=secret,
        hash_client_secret=True,
    )
    client = ApiClient.objects.create(
        realm_id=maker.realm_id,
        name=name,
        application=application,
        client_id=application.client_id,
        permissions=wanted,
        created_by=maker.user,
    )
    return client, secret


@transaction.atomic
def revoke_client(client: ApiClient) -> ApiClient:
    """Stop the client at once: its application and every token it holds are deleted."""
    if client.revoked_at is None:
        application = client.application
        client.revoked_at = timezone.now()
        client.application = None
        client.save(update_fields=["revoked_at", "application"])
        if application is not None:
            application.delete()
    return client
