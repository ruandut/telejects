from rest_framework.test import APIClient

from conftest import TEST_PASSWORD


def _sign_in(email, password):
    return APIClient().post(
        "/api/auth/token/", {"email": email, "password": password}, format="json"
    )


def test_sign_in_returns_tokens_that_work(user, realm):
    res = _sign_in(user.email, TEST_PASSWORD)
    assert res.status_code == 200
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['access']}")
    me = client.get("/api/auth/me/").json()
    assert me["email"] == user.email
    assert me["realm"]["id"] == realm.id


def test_sign_in_ignores_email_capitalisation(user):
    assert _sign_in("  Tester@Example.com ", TEST_PASSWORD).status_code == 200


def test_wrong_password_is_refused(user):
    assert _sign_in(user.email, "not-the-password").status_code == 401


def test_inactive_user_is_refused(user):
    user.is_active = False
    user.save()
    assert _sign_in(user.email, TEST_PASSWORD).status_code == 401


def test_refresh_gives_a_new_access_token(user):
    refresh = _sign_in(user.email, TEST_PASSWORD).json()["refresh"]
    res = APIClient().post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert res.status_code == 200
    assert res.json()["access"]


def test_sign_in_is_throttled(user):
    statuses = [_sign_in(user.email, "not-the-password").status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
