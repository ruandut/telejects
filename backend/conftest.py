import secrets

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

# Generated per test run, so not even a throwaway password is written in the repo.
TEST_PASSWORD = secrets.token_urlsafe(16)


def make_user(email: str):
    return get_user_model().objects.create_user(email=email, password=TEST_PASSWORD)


def client_for(user) -> APIClient:
    """An API client signed in as `user`."""
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture(autouse=True)
def _fresh_throttles():
    """Throttle counters live in the cache; don't let one test's sign-ins count against another."""
    cache.clear()


@pytest.fixture
def user(db):
    return make_user("tester@example.com")


@pytest.fixture
def api(user):
    return client_for(user)
