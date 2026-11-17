import re
import secrets

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as outbox
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.realms.access_control import ADMIN
from apps.realms.services import add_member, create_realm

# Generated per test run, so not even a throwaway password is written in the repo.
TEST_PASSWORD = secrets.token_urlsafe(16)
# For confirming an invitation: a strong password, also generated per run.
NEW_PASSWORD = secrets.token_urlsafe(18)


def make_user(email: str):
    return get_user_model().objects.create_user(email=email, password=TEST_PASSWORD)


def member(realm, email: str, role_key: str = "field_technician", name: str = ""):
    """An active user of `realm` with that built-in role (an existing account is reused)."""
    users = get_user_model().objects
    user = users.filter(email=email).first() or make_user(email)
    return add_member(realm, user, role_key, name=name)


def client_for(user, realm=None) -> APIClient:
    """An API client signed in as `user`, optionally naming the company its requests work in."""
    client = APIClient()
    client.force_authenticate(user)
    if realm is not None:
        client.credentials(HTTP_X_REALM=str(realm.id))
    return client


def sent_token(to: str) -> str:
    """The token in the last invitation email sent to `to`."""
    for message in reversed(outbox.outbox):
        if to in message.to:
            return re.search(r"token=([\w-]+)", message.body).group(1)
    raise AssertionError(f"No email to {to}")


@pytest.fixture(autouse=True)
def _mail_sent_inline(monkeypatch):
    """Invitation emails go straight to Django's test outbox instead of through Hatchet."""
    from apps.users import mail, services

    monkeypatch.setattr(services, "_after_commit", lambda func: func())
    monkeypatch.setattr(mail, "enqueue_invitation", mail.deliver_invitation)


@pytest.fixture(autouse=True)
def _fresh_throttles():
    """Throttle counters live in the cache; don't let one test's sign-ins count against another."""
    cache.clear()


@pytest.fixture
def user(db):
    return make_user("tester@example.com")


@pytest.fixture
def realm(user):
    """Northwind Fibre, where the tester is the only Admin."""
    realm = create_realm("Northwind Fibre")
    add_member(realm, user, ADMIN, name="Tess Tester")
    return realm


@pytest.fixture
def api(user, realm):
    return client_for(user, realm)
