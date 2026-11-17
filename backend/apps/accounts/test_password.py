"""Spec 0002: changing my password. Each scenario's test is named test_at_0002_<nn>_<what>.
Passwords here are generated per run, never written in the repo."""

import secrets

import pytest
from django.core import mail as outbox
from rest_framework.test import APIClient

from conftest import TEST_PASSWORD, client_for, member

URL = "/api/auth/password/"


def new_password() -> str:
    return secrets.token_urlsafe(16)


def signed_in(email, password) -> tuple[APIClient, dict]:
    """A browser signed in the way the app does it: with tokens from the sign-in endpoint."""
    tokens = (
        APIClient()
        .post("/api/auth/token/", {"email": email, "password": password}, format="json")
        .json()
    )
    browser = APIClient()
    browser.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return browser, tokens


def can_sign_in(email, password) -> bool:
    res = APIClient().post("/api/auth/token/", {"email": email, "password": password}, "json")
    return res.status_code == 200


def change(client, current, new):
    return client.post(URL, {"current_password": current, "new_password": new}, "json")


def test_at_0002_01_my_settings_work_in_any_company_or_none(user, realm):
    # The page is reached from the account menu; the API behind it needs no company.
    no_company = client_for(user)
    assert change(no_company, TEST_PASSWORD, first := new_password()).status_code == 200
    in_company = client_for(user, realm)
    assert change(in_company, first, new_password()).status_code == 200


def test_at_0002_02_i_change_my_password_with_my_current_one(user):
    password = new_password()
    browser, _ = signed_in(user.email, TEST_PASSWORD)
    res = change(browser, TEST_PASSWORD, password)
    assert res.status_code == 200
    assert can_sign_in(user.email, password)
    assert not can_sign_in(user.email, TEST_PASSWORD)
    # Nothing sent back is a password.
    assert set(res.json()) == {"access", "refresh"}


def test_at_0002_03_a_wrong_current_password_changes_nothing(user):
    res = change(client_for(user), "not-my-password", new_password())
    assert res.status_code == 400
    assert res.json()["current_password"] == ["That isn't your current password."]
    assert can_sign_in(user.email, TEST_PASSWORD)
    assert len(outbox.outbox) == 0


@pytest.mark.parametrize(
    "weak", ["short1", "password123", "83920174652", "tester@example.com"]
)  # fmt: skip
def test_at_0002_04_the_new_password_must_be_a_good_one(user, weak):
    res = change(client_for(user), TEST_PASSWORD, weak)
    assert res.status_code == 400
    assert res.json()["new_password"]
    assert can_sign_in(user.email, TEST_PASSWORD)


def test_at_0002_05_the_new_password_must_be_new(user):
    res = change(client_for(user), TEST_PASSWORD, TEST_PASSWORD)
    assert res.status_code == 400
    assert res.json()["new_password"] == ["Choose a password you aren't using now."]


def test_at_0002_06_changing_it_signs_out_my_other_browsers(user):
    this, _ = signed_in(user.email, TEST_PASSWORD)
    other, other_tokens = signed_in(user.email, TEST_PASSWORD)
    fresh = change(this, TEST_PASSWORD, new_password()).json()

    # This browser carries on with the tokens it was given.
    this.credentials(HTTP_AUTHORIZATION=f"Bearer {fresh['access']}")
    assert this.get("/api/auth/me/").status_code == 200
    refreshed = APIClient().post("/api/auth/token/refresh/", {"refresh": fresh["refresh"]}, "json")
    assert refreshed.status_code == 200

    # The other is refused, and can't refresh its way back in.
    assert other.get("/api/auth/me/").status_code == 401
    res = APIClient().post("/api/auth/token/refresh/", {"refresh": other_tokens["refresh"]}, "json")
    assert res.status_code == 401


def test_at_0002_07_im_told_by_email(user):
    password = new_password()
    change(client_for(user), TEST_PASSWORD, password)
    [email] = outbox.outbox
    assert email.to == [user.email]
    assert "password" in email.subject.lower()
    assert password not in email.body
    assert TEST_PASSWORD not in email.body


def test_at_0002_08_guessing_is_slowed_down(user):
    client = client_for(user)
    statuses = [change(client, "guess", new_password()).status_code for _ in range(11)]
    assert statuses[:10] == [400] * 10
    assert statuses[10] == 429
    # Even the right password waits now.
    assert change(client, TEST_PASSWORD, new_password()).status_code == 429
    assert can_sign_in(user.email, TEST_PASSWORD)


def test_at_0002_09_only_my_own_password_and_only_signed_in(user, realm):
    assert change(APIClient(), TEST_PASSWORD, new_password()).status_code == 401
    colleague = member(realm, "colleague@example.com").user
    # Naming someone else changes nothing for them: the request is about me.
    res = client_for(user, realm).post(
        URL,
        {"current_password": TEST_PASSWORD, "new_password": new_password(),
         "user": colleague.id, "email": colleague.email},
        "json",
    )  # fmt: skip
    assert res.status_code == 200
    assert can_sign_in(colleague.email, TEST_PASSWORD)
    assert not can_sign_in(user.email, TEST_PASSWORD)
