"""Spec 0001: user management inside one company. Isolation scenarios (29 to 34) live in
apps/realms/test_isolation.py."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail as outbox
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.realms.access_control import ADMIN
from apps.realms.models import Realm, RealmMembership, Role
from apps.realms.services import create_realm
from apps.users.models import Invitation
from conftest import NEW_PASSWORD, TEST_PASSWORD, client_for, make_user, member, sent_token


def role_id(realm, key):
    return Role.objects.in_realm(realm).by_key(key).id


def people(api):
    return {row["email"]: row for row in api.get("/api/users/").json()}


def add(api, realm, email="thandi@example.com", name="Thandi Nkosi", role="field_technician"):
    return api.post(
        "/api/users/",
        {"email": email, "name": name, "role": role_id(realm, role)},
        format="json",
    )


def sign_in(email, password):
    return APIClient().post(
        "/api/auth/token/", {"email": email, "password": password}, format="json"
    )


def accept(token, password=None):
    body = {} if password is None else {"password": password}
    return APIClient().post(f"/api/users/invitations/{token}/", body, format="json")


# --- managing users ----------------------------------------------------------------------------


def test_at_0001_01_an_admin_sees_the_companys_users(api, realm):
    member(realm, "sam@example.com", "project_manager", name="Sam Pillay")
    rows = people(api)
    assert set(rows) == {"tester@example.com", "sam@example.com"}
    sam = rows["sam@example.com"]
    assert sam["name"] == "Sam Pillay"
    assert sam["role"]["name"] == "Project manager"
    assert sam["status"] == "active"
    assert rows["tester@example.com"]["is_me"] is True


def test_at_0001_02_an_admin_adds_a_user(api, realm):
    res = add(api, realm)
    assert res.status_code == 201
    row = people(api)["thandi@example.com"]
    assert (row["name"], row["role"]["name"], row["status"]) == (
        "Thandi Nkosi",
        "Field technician",
        "invited",
    )
    [message] = outbox.outbox
    assert message.to == ["thandi@example.com"]
    assert "Northwind Fibre" in message.subject
    assert "/accept-invite?token=" in message.body


def test_at_0001_03_the_same_email_cant_be_added_twice(api, realm):
    add(api, realm)
    outbox.outbox.clear()
    res = add(api, realm, email="Thandi@Example.com")
    assert res.status_code == 400
    assert res.json()["email"] == "They're already a user here."
    assert outbox.outbox == []


def test_at_0001_04_an_admin_edits_a_user(api, realm):
    thandi = member(realm, "thandi@example.com", "field_technician", name="Thandi Nkosi")
    res = api.patch(
        f"/api/users/{thandi.id}/",
        {"name": "Thandi Dlamini", "role": role_id(realm, "project_manager")},
        format="json",
    )
    assert res.status_code == 200
    row = people(api)["thandi@example.com"]
    assert (row["name"], row["role"]["name"]) == ("Thandi Dlamini", "Project manager")


def test_at_0001_05_an_admin_removes_a_user(api, realm):
    thandi = member(realm, "thandi@example.com", "project_manager", name="Thandi Nkosi")
    assert api.delete(f"/api/users/{thandi.id}/").status_code == 204
    assert "thandi@example.com" not in people(api)
    her = client_for(thandi.user, realm)
    assert her.get("/api/users/").status_code == 403
    assert her.get("/api/auth/me/").json()["realm"] is None


def test_at_0001_06_without_the_permission_users_cant_be_managed(realm):
    pm = member(realm, "pm@example.com", "project_manager")
    other = member(realm, "sam@example.com", "field_technician")
    client = client_for(pm.user, realm)
    assert client.get("/api/users/").status_code == 200
    assert client.get(f"/api/users/{other.id}/").status_code == 200
    attempts = [
        client.post(
            "/api/users/",
            {"email": "x@example.com", "name": "X", "role": role_id(realm, "viewer")},
            format="json",
        ),
        client.patch(f"/api/users/{other.id}/", {"name": "Changed"}, format="json"),
        client.patch(f"/api/users/{other.id}/", {"role": role_id(realm, ADMIN)}, format="json"),
        client.delete(f"/api/users/{other.id}/"),
        client.post(f"/api/users/{other.id}/resend/"),
    ]
    assert [r.status_code for r in attempts] == [403] * 5
    other.refresh_from_db()
    assert (other.name, other.role.key, other.status) == ("", "field_technician", "active")
    assert outbox.outbox == []


@pytest.mark.parametrize("key", ["field_technician", "viewer"])
def test_at_0001_07_some_roles_dont_see_users_at_all(realm, key):
    someone = member(realm, f"{key}@example.com", key)
    client = client_for(someone.user, realm)
    assert client.get("/api/users/").status_code == 403
    assert client.get("/api/roles/").status_code == 403
    assert client.get("/api/auth/me/").json()["realm"]["permissions"] == []


def test_at_0001_08_an_admin_cancels_an_invitation(api, realm):
    add(api, realm, email="sam@example.com", name="Sam Pillay")
    token = sent_token("sam@example.com")
    sam = people(api)["sam@example.com"]
    assert api.delete(f"/api/users/{sam['id']}/").status_code == 204
    assert "sam@example.com" not in people(api)
    res = APIClient().get(f"/api/users/invitations/{token}/")
    assert res.status_code == 404


# --- always an Admin ----------------------------------------------------------------------------


def _me(realm, user):
    return RealmMembership.objects.in_realm(realm).get(user=user)


def test_at_0001_09_removing_the_only_admin_hands_the_role_over(api, realm, user):
    thandi = member(realm, "thandi@example.com", "field_technician")
    me = _me(realm, user)
    res = api.delete(f"/api/users/{me.id}/", {"new_admin": thandi.id}, format="json")
    assert res.status_code == 204
    thandi.refresh_from_db()
    assert thandi.is_admin
    assert api.get("/api/users/").status_code == 403


def test_at_0001_10_the_only_admin_cant_be_removed_without_a_successor(api, realm, user):
    member(realm, "thandi@example.com", "field_technician")
    me = _me(realm, user)
    res = api.delete(f"/api/users/{me.id}/")
    assert res.status_code == 400
    assert res.json()["new_admin"] == "Choose who takes over as Admin."
    me.refresh_from_db()
    assert me.is_active and me.is_admin


def test_at_0001_11_the_successor_must_be_an_active_user(api, realm, user):
    add(api, realm, email="sam@example.com")
    sam = people(api)["sam@example.com"]
    member(realm, "thandi@example.com", "field_technician")
    me = _me(realm, user)
    res = api.delete(f"/api/users/{me.id}/", {"new_admin": sam["id"]}, format="json")
    assert res.status_code == 400
    assert _me(realm, user).is_admin


def test_the_only_active_user_cant_be_removed(api, realm, user):
    res = api.delete(f"/api/users/{_me(realm, user).id}/")
    assert res.status_code == 400
    assert _me(realm, user).is_active


def test_at_0001_12_the_only_admins_role_cant_be_changed(api, realm, user):
    me = _me(realm, user)
    res = api.patch(
        f"/api/users/{me.id}/", {"role": role_id(realm, "project_manager")}, format="json"
    )
    assert res.status_code == 400
    assert res.json()["role"] == "A company needs at least one Admin."
    assert _me(realm, user).is_admin


def test_at_0001_13_with_another_admin_no_successor_is_needed(api, realm):
    thandi = member(realm, "thandi@example.com", ADMIN)
    assert api.delete(f"/api/users/{thandi.id}/").status_code == 204


# --- roles ---------------------------------------------------------------------------------------


def test_at_0001_15_i_pick_a_role_when_adding_someone(api, realm):
    roles = api.get("/api/roles/").json()
    assert [r["name"] for r in roles] == ["Admin", "Project manager", "Field technician", "Viewer"]
    assert all(r["description"] for r in roles)
    pm = next(r for r in roles if r["key"] == "project_manager")
    assert [p["code"] for p in pm["permissions"]] == ["users.view"]

    res = api.post("/api/users/", {"email": "x@example.com", "name": "No Role"}, format="json")
    assert res.status_code == 400
    assert "role" in res.json()
    assert outbox.outbox == []


def test_at_0001_16_a_changed_role_takes_effect_at_once(api, realm):
    thandi = member(realm, "thandi@example.com", "project_manager")
    hers = client_for(thandi.user, realm)
    assert hers.get("/api/users/").status_code == 200
    api.patch(
        f"/api/users/{thandi.id}/",
        {"role": role_id(realm, "field_technician")},
        format="json",
    )
    assert hers.get("/api/users/").status_code == 403


def test_at_0001_18_my_permissions_come_with_who_i_am(user, realm):
    res = APIClient().post(
        "/api/auth/token/", {"email": user.email, "password": TEST_PASSWORD}, format="json"
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['access']}")
    me = client.get("/api/auth/me/").json()
    assert me["name"] == "Tess Tester"
    assert me["realm"]["name"] == "Northwind Fibre"
    assert me["realm"]["role"]["key"] == ADMIN
    assert me["realm"]["permissions"] == ["users.manage", "users.view"]

    pm = member(realm, "pm@example.com", "project_manager")
    assert client_for(pm.user, realm).get("/api/auth/me/").json()["realm"]["permissions"] == [
        "users.view"
    ]


# --- confirming an account ----------------------------------------------------------------------


def test_at_0001_19_a_new_user_confirms_their_account(api, realm):
    add(api, realm)
    token = sent_token("thandi@example.com")
    info = APIClient().get(f"/api/users/invitations/{token}/").json()
    assert info == {
        "realm_name": "Northwind Fibre",
        "email": "thandi@example.com",
        "needs_password": True,
    }
    res = accept(token, NEW_PASSWORD)
    assert res.status_code == 200
    body = res.json()
    assert body["signed_in"] is True and body["realm_id"] == realm.id
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {body['access']}")
    assert client.get("/api/auth/me/").json()["realm"]["name"] == "Northwind Fibre"
    assert people(api)["thandi@example.com"]["status"] == "active"


def test_at_0001_20_someone_with_an_account_joins_another_company(api, realm):
    blue = create_realm("Blue Mast Telecom")
    lerato = member(blue, "lerato@example.com", "viewer")
    add(api, realm, email="lerato@example.com", name="Lerato Mokoena")
    token = sent_token("lerato@example.com")
    assert APIClient().get(f"/api/users/invitations/{token}/").json()["needs_password"] is False

    res = accept(token)
    assert res.json() == {"signed_in": False, "realm_id": realm.id}
    assert sign_in("lerato@example.com", TEST_PASSWORD).status_code == 200
    me = client_for(lerato.user).get("/api/auth/me/").json()
    assert {r["name"] for r in me["realms"]} == {"Northwind Fibre", "Blue Mast Telecom"}


def test_at_0001_21_an_invited_user_cant_work_before_confirming(api, realm):
    add(api, realm)
    assert sign_in("thandi@example.com", "").status_code in (400, 401)
    assert sign_in("thandi@example.com", NEW_PASSWORD).status_code == 401

    # Someone with an account elsewhere can sign in, but not work in this company yet.
    blue = create_realm("Blue Mast Telecom")
    lerato = member(blue, "lerato@example.com", "viewer")
    add(api, realm, email="lerato@example.com")
    client = client_for(lerato.user, realm)
    assert client.get("/api/auth/me/").json()["realm"] is None
    assert client.get("/api/roles/").status_code == 403


def test_at_0001_22_a_link_works_once(api, realm):
    add(api, realm)
    token = sent_token("thandi@example.com")
    accept(token, NEW_PASSWORD)
    res = APIClient().get(f"/api/users/invitations/{token}/")
    assert res.status_code == 410
    assert res.json()["detail"] == "This link has already been used."
    assert accept(token, NEW_PASSWORD + "x").status_code == 410


def test_at_0001_23_a_link_expires(api, realm):
    add(api, realm)
    token = sent_token("thandi@example.com")
    Invitation.objects.in_realm(realm).update(expires_at=timezone.now() - timedelta(minutes=1))
    res = APIClient().get(f"/api/users/invitations/{token}/")
    assert res.status_code == 410
    assert res.json()["detail"] == "This link has expired. Ask your administrator for a new one."


def test_at_0001_24_an_admin_resends_the_invitation(api, realm):
    add(api, realm)
    first = sent_token("thandi@example.com")
    thandi = people(api)["thandi@example.com"]
    assert api.post(f"/api/users/{thandi['id']}/resend/").status_code == 204
    second = sent_token("thandi@example.com")
    assert len(outbox.outbox) == 2 and first != second
    assert APIClient().get(f"/api/users/invitations/{first}/").status_code == 404
    assert APIClient().get(f"/api/users/invitations/{second}/").status_code == 200


def test_at_0001_25_a_weak_password_is_refused(api, realm):
    add(api, realm)
    token = sent_token("thandi@example.com")
    res = accept(token, "password")
    assert res.status_code == 400
    assert res.json()["password"]
    assert people(api)["thandi@example.com"]["status"] == "invited"


def test_a_garbage_token_is_not_found(db):
    assert APIClient().get("/api/users/invitations/nonsense/").status_code == 404


def test_the_token_is_never_stored(api, realm):
    add(api, realm)
    token = sent_token("thandi@example.com")
    stored = Invitation.objects.in_realm(realm).get()
    assert stored.token_hash and token not in stored.token_hash


def test_a_removed_user_can_be_added_again(api, realm):
    thandi = member(realm, "thandi@example.com", "viewer")
    api.delete(f"/api/users/{thandi.id}/")
    assert add(api, realm).status_code == 201
    assert people(api)["thandi@example.com"]["status"] == "invited"


# --- companies -----------------------------------------------------------------------------------


def test_at_0001_26_i_work_in_one_company_at_a_time(user, realm):
    blue = create_realm("Blue Mast Telecom")
    member(blue, user.email, ADMIN, name="Tess at Blue Mast")
    member(blue, "lerato@example.com", "viewer")

    north = client_for(user, realm).get("/api/users/").json()
    blue_rows = client_for(user, blue).get("/api/users/").json()
    assert {r["email"] for r in north} == {"tester@example.com"}
    assert {r["email"] for r in blue_rows} == {"tester@example.com", "lerato@example.com"}
    assert client_for(user, blue).get("/api/auth/me/").json()["realm"]["name"] == (
        "Blue Mast Telecom"
    )


def test_without_a_header_the_oldest_company_is_used(user, realm):
    blue = create_realm("Blue Mast Telecom")
    member(blue, user.email, ADMIN)
    assert client_for(user).get("/api/auth/me/").json()["realm"]["id"] == realm.id


def test_at_0001_27_someone_in_no_company(db):
    nobody = make_user("nobody@example.com")
    me = client_for(nobody).get("/api/auth/me/").json()
    assert me["realm"] is None and me["realms"] == []
    res = client_for(nobody).get("/api/users/")
    assert res.status_code == 403
    assert res.json()["code"] == "no_realm"


def test_at_0001_28_platform_staff_add_a_company(db):
    out = StringIO()
    call_command("create_company", "Northwind Fibre", "Boss@Example.com", stdout=out)
    realm = Realm.objects.get(name="Northwind Fibre")
    assert Role.objects.in_realm(realm).count() == 4
    admin = RealmMembership.objects.in_realm(realm).get()
    assert admin.user.email == "boss@example.com"
    assert admin.is_admin and admin.status == "invited"
    assert outbox.outbox[0].to == ["boss@example.com"]
    accept(sent_token("boss@example.com"), NEW_PASSWORD)
    admin.refresh_from_db()
    assert admin.is_active
