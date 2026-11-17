"""No endpoint shows, changes or links to another company's data, and nobody acts in a company
they don't belong to, or beyond their permissions.

Every new endpoint adds its cases here, in the same change (see CLAUDE.md), covering:
  1. another company's rows stay out of lists, counts and aggregates;
  2. detail routes and actions on another company's rows are 404 for every method, and the row
     is unchanged;
  3. a foreign key in a request body can't point into another company;
  4. a non-member naming the company in X-Realm gets 403;
  5. permission limits hold.
The guard tests at the bottom fail when a route, model or query skips the pattern.
"""

import ast
from pathlib import Path

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import mail as outbox
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from apps.realms.access_control import ADMIN
from apps.realms.models import RealmMembership, Role, TenantModel
from apps.realms.permissions import InRealm
from apps.realms.services import create_realm
from conftest import NEW_PASSWORD, client_for, member, sent_token

APPS_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def blue(db):
    """Blue Mast Telecom: another company. The tester is not a member."""
    realm = create_realm("Blue Mast Telecom")
    owner = member(realm, "owner@example.com", ADMIN, name="Olu Owner")
    lerato = member(realm, "lerato@example.com", "project_manager", name="Lerato Mokoena")
    return {"realm": realm, "owner": owner, "lerato": lerato}


def _snapshot(membership):
    membership.refresh_from_db()
    return (membership.name, membership.role_id, membership.status)


# --- the X-Realm header: you can't work in a company you aren't in ------------------------------

COMPANY_ROUTES = ["/api/users/", "/api/roles/"]


@pytest.mark.parametrize("path", COMPANY_ROUTES)
def test_naming_another_company_is_refused(user, realm, blue, path):
    res = client_for(user, blue["realm"]).get(path)
    assert res.status_code == 403
    assert res.json()["code"] == "not_member"
    assert "Blue Mast" not in res.content.decode()


@pytest.mark.parametrize("path", COMPANY_ROUTES)
def test_a_missing_or_garbage_company_gets_the_same_refusal(user, realm, blue, path):
    foreign = client_for(user, blue["realm"]).get(path)
    missing = client_for(user).get(path, HTTP_X_REALM="999999")
    garbage = client_for(user).get(path, HTTP_X_REALM="1 OR 1=1")
    assert foreign.status_code == missing.status_code == garbage.status_code == 403
    assert foreign.json() == missing.json() == garbage.json()


def test_invited_and_removed_members_have_no_access(user, realm):
    membership = RealmMembership.objects.in_realm(realm).get(user=user)
    client = client_for(user, realm)
    for status in ("invited", "removed"):
        membership.status = status
        membership.save()
        assert client.get("/api/users/").status_code == 403
        assert client.get("/api/auth/me/").json()["realm"] is None


def test_me_never_mentions_another_company(user, realm, blue):
    me = client_for(user).get("/api/auth/me/").json()
    assert [r["id"] for r in me["realms"]] == [realm.id]
    res = client_for(user, blue["realm"]).get("/api/auth/me/")
    assert res.status_code == 200
    assert res.json()["realm"] is None
    assert "Blue Mast" not in res.content.decode()


# --- users ---------------------------------------------------------------------------------------


def test_at_0001_29_another_companys_users_are_invisible(api, blue):
    body = api.get("/api/users/").content.decode()
    assert "lerato@example.com" not in body and "Lerato" not in body
    lerato = blue["lerato"]
    before = _snapshot(lerato)
    path = f"/api/users/{lerato.id}/"
    assert api.get(path).status_code == 404
    assert api.patch(path, {"name": "Changed"}, format="json").status_code == 404
    assert api.put(path, {"name": "Changed"}, format="json").status_code in (404, 405)
    assert api.delete(path).status_code == 404
    assert api.post(f"{path}resend/").status_code == 404
    assert _snapshot(lerato) == before
    assert outbox.outbox == []


def test_another_companys_user_looks_the_same_as_a_missing_one(api, blue):
    foreign = api.get(f"/api/users/{blue['lerato'].id}/")
    missing = api.get("/api/users/999999/")
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())


def test_at_0001_30_an_admin_elsewhere_cant_act_here(realm, blue):
    outsider = client_for(blue["owner"].user, realm)
    mine = RealmMembership.objects.in_realm(realm).get()
    before = _snapshot(mine)
    attempts = [
        outsider.get("/api/users/"),
        outsider.post(
            "/api/users/",
            {
                "email": "x@example.com",
                "name": "X",
                "role": Role.objects.in_realm(realm).first().id,
            },
            format="json",
        ),
        outsider.get(f"/api/users/{mine.id}/"),
        outsider.patch(f"/api/users/{mine.id}/", {"name": "Hacked"}, format="json"),
        outsider.delete(f"/api/users/{mine.id}/"),
        outsider.post(f"/api/users/{mine.id}/resend/"),
        outsider.get("/api/roles/"),
    ]
    assert [r.status_code for r in attempts] == [403] * len(attempts)
    assert _snapshot(mine) == before
    assert RealmMembership.objects.in_realm(realm).count() == 1


def test_at_0001_31_adding_a_user_never_reveals_other_companies(api, realm, blue):
    tech = Role.objects.in_realm(realm).by_key("viewer").id
    known = api.post(
        "/api/users/", {"email": "lerato@example.com", "name": "L", "role": tech}, format="json"
    )
    new = api.post(
        "/api/users/", {"email": "fresh@example.com", "name": "L", "role": tech}, format="json"
    )
    assert known.status_code == new.status_code == 201

    def shape(body):
        return {k: v for k, v in body.items() if k not in ("id", "email", "joined_at")}

    assert shape(known.json()) == shape(new.json())
    assert "Lerato Mokoena" not in known.content.decode()
    assert "Project manager" not in known.content.decode()
    # Her membership elsewhere is untouched.
    assert _snapshot(blue["lerato"])[2] == "active"


def test_at_0001_32_a_successor_cant_come_from_another_company(api, user, realm, blue):
    member(realm, "thandi@example.com", "viewer")
    mine = RealmMembership.objects.in_realm(realm).get(user=user)
    before_theirs = _snapshot(blue["lerato"])
    res = api.delete(f"/api/users/{mine.id}/", {"new_admin": blue["lerato"].id}, format="json")
    assert res.status_code == 400
    assert res.json()["new_admin"] == "Choose who takes over as Admin."
    assert _snapshot(mine)[2] == "active"
    assert _snapshot(blue["lerato"]) == before_theirs


def test_at_0001_34_a_role_cant_come_from_another_company(api, realm, blue):
    foreign_admin = Role.objects.in_realm(blue["realm"]).by_key(ADMIN).id
    added = api.post(
        "/api/users/",
        {"email": "x@example.com", "name": "X", "role": foreign_admin},
        format="json",
    )
    assert added.status_code == 400 and "role" in added.json()
    assert outbox.outbox == []

    thandi = member(realm, "thandi@example.com", "viewer")
    edited = api.patch(f"/api/users/{thandi.id}/", {"role": foreign_admin}, format="json")
    assert edited.status_code == 400 and "role" in edited.json()
    assert _snapshot(thandi)[1] == Role.objects.in_realm(realm).by_key("viewer").id

    roles = api.get("/api/roles/").json()
    assert {r["id"] for r in roles} == set(
        Role.objects.in_realm(realm).values_list("id", flat=True)
    )
    assert api.get(f"/api/roles/{foreign_admin}/").status_code == 404


def test_an_invitation_link_only_opens_its_own_company(api, realm, blue):
    api.post(
        "/api/users/",
        {
            "email": "sam@example.com",
            "name": "Sam",
            "role": Role.objects.in_realm(realm).by_key("viewer").id,
        },
        format="json",
    )
    token = sent_token("sam@example.com")
    body = APIClient().get(f"/api/users/invitations/{token}/").json()
    assert body["realm_name"] == "Northwind Fibre"
    assert set(body) == {"realm_name", "email", "needs_password"}
    APIClient().post(f"/api/users/invitations/{token}/", {"password": NEW_PASSWORD}, format="json")
    sam = get_user_model().objects.get(email="sam@example.com")
    assert [m.realm_id for m in RealmMembership.objects.of_user(sam)] == [realm.id]


def test_permission_limits_hold_for_roles(realm):
    viewer = member(realm, "viewer@example.com", "viewer")
    assert client_for(viewer.user, realm).get("/api/roles/").status_code == 403
    pm = member(realm, "pm@example.com", "project_manager")
    assert client_for(pm.user, realm).get("/api/roles/").status_code == 200


def test_roles_are_read_only(api, realm):
    role = Role.objects.in_realm(realm).first()
    assert api.post("/api/roles/", {"key": "x", "name": "X"}, format="json").status_code == 405
    assert api.patch(f"/api/roles/{role.id}/", {"name": "X"}, format="json").status_code == 405
    assert api.delete(f"/api/roles/{role.id}/").status_code == 405


# --- signed out: nothing but the public routes ----------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/me/",
        "/api/auth/password/",
        "/api/users/",
        "/api/users/1/",
        "/api/roles/",
        "/api/roles/1/",
    ],
)
def test_signed_out_requests_are_refused(db, path):
    assert APIClient().get(path).status_code == 401


# --- guards: the pattern can't be skipped quietly -------------------------------------------------

# Routes that deliberately don't use InRealm, each with the reason. Adding to this list is a
# decision to review, not a way to make the test pass.
NOT_REALM_GATED = {
    "health": "public liveness check; returns no data",
    "token_obtain_pair": "sign-in happens before there is a user",
    "token_refresh": "exchanges the user's own refresh token",
    "me": "the user's own identity and memberships; resolves the company itself",
    "password": "changes only the signed-in person's own password, whichever company (0002)",
    "user-invitation": "confirming an account by emailed link, before there is a password; "
    "tells the token's holder only the company name and their own address",
}

# Models that aren't rows inside a company, each with the reason.
NOT_TENANT_MODELS = {
    "accounts.User": "people exist across companies; access comes from memberships",
    "realms.Realm": "the tenant itself",
    "realms.RealmMembership": "links a user to a company; its queryset is still strict",
}

# Every `.across_realms()` call outside tests, by file and enclosing function, with the reason.
ACROSS_REALMS_CALLS = {
    "realms/querysets.py::RealmMembershipQuerySet.of_user": "a user's own memberships, to "
    "find which companies they may work in; filtered by user",
    "users/querysets.py::InvitationQuerySet.by_token_hash": "the public invitation link: the "
    "token is the only thing naming the company",
    "realms/admin.py::_across": "Django admin, for platform staff",
}


def _api_routes(resolver=None, prefix=""):
    for entry in (resolver or get_resolver()).url_patterns:
        path = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _api_routes(entry, path)
        elif isinstance(entry, URLPattern) and path.startswith("api/"):
            yield path, entry


def _permission_classes(pattern: URLPattern) -> list:
    """The permission classes each of the route's handlers runs with."""
    view = pattern.callback
    cls = view.cls
    found = []
    for handler in getattr(view, "actions", None) or {}:
        method = getattr(cls, view.actions[handler])
        found.append(
            getattr(method, "kwargs", {}).get("permission_classes", cls.permission_classes)
        )
    return found or [cls.permission_classes]


def ungated_routes() -> set[str]:
    ungated = set()
    for path, pattern in _api_routes():
        assert hasattr(pattern.callback, "cls"), f"{path} is not a DRF view"
        if all(InRealm in classes for classes in _permission_classes(pattern)):
            continue
        ungated.add(pattern.name)
    return ungated


def non_tenant_models() -> set[str]:
    ours = [m for m in apps.get_models() if m.__module__.startswith("apps.")]
    return {m._meta.label for m in ours if not issubclass(m, TenantModel)}


def across_realms_calls() -> set[str]:
    found = set()
    for path in APPS_DIR.rglob("*.py"):
        if path.name.startswith("test_") or "migrations" in path.parts:
            continue
        found |= _calls_in(ast.parse(path.read_text()), str(path.relative_to(APPS_DIR)))
    return found


def _calls_in(tree, filename) -> set[str]:
    found = set()

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(child, [*scope, child.name])
                continue
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "across_realms"
            ):
                found.add(f"{filename}::{'.'.join(scope) or '<module>'}")
            visit(child, scope)

    visit(tree, [])
    return found


def test_at_0001_33_every_api_route_is_company_gated_or_listed():
    assert ungated_routes() == set(NOT_REALM_GATED)


def test_at_0001_33_every_model_belongs_to_a_company_or_is_listed():
    assert non_tenant_models() == set(NOT_TENANT_MODELS)


def test_every_across_realms_call_is_listed():
    assert across_realms_calls() == set(ACROSS_REALMS_CALLS)


def test_at_0001_33_the_guards_catch_a_skipped_pattern():
    """The checks the guards run do flag an unlisted call, an ungated view and a plain model."""
    sneaky = ast.parse("def leak():\n    return Thing.objects.across_realms()\n")
    assert _calls_in(sneaky, "x/views.py") == {"x/views.py::leak"}

    from rest_framework.permissions import IsAuthenticated
    from rest_framework.views import APIView

    class Ungated(APIView):
        permission_classes = [IsAuthenticated]

    pattern = URLPattern("api/leak/", Ungated.as_view(), name="leak")
    assert InRealm not in _permission_classes(pattern)[0]

    assert not issubclass(RealmMembership, TenantModel)  # hence its entry in the list
