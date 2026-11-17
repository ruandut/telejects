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
import json
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

COMPANY_ROUTES = [
    "/api/users/",
    "/api/roles/",
    "/api/integrations/connectors/",
    "/api/integrations/connections/",
    "/api/feasibilities/runs/",
    "/api/feasibilities/runs/products/",
]


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
        "/api/integrations/connectors/",
        "/api/integrations/connections/",
        "/api/integrations/connections/1/",
        "/api/integrations/connections/1/products/",
        "/api/feasibilities/runs/",
        "/api/feasibilities/runs/1/",
        "/api/feasibilities/runs/1/sites/",
        "/api/feasibilities/runs/1/export/",
        "/api/feasibilities/runs/products/",
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
    "integrations.ConnectorDefinition": "the platform's connector catalogue, the same for every "
    "company and read-only to them; holds no company data (0003)",
    "integrations.PlatformAccount": "Telejects' own provider credentials, kept by platform staff; "
    "a company only reaches one through its own PlatformGrant and never sees its settings or "
    "secrets (0004)",
}

# Every `.across_realms()` call outside tests, by file and enclosing function, with the reason.
ACROSS_REALMS_CALLS = {
    "realms/querysets.py::RealmMembershipQuerySet.of_user": "a user's own memberships, to "
    "find which companies they may work in; filtered by user",
    "users/querysets.py::InvitationQuerySet.by_token_hash": "the public invitation link: the "
    "token is the only thing naming the company",
    "realms/admin.py::_across": "Django admin, for platform staff",
    "integrations/services.py::due_operations": "the hourly scheduler finds every company's "
    "due syncs; each then runs with its own company's id (0003)",
    "integrations/services.py::_publish_platform": "tells each company using a platform account "
    "that its connections changed (ids only); the socket then checks each subscriber (0004)",
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


# --- integrations and feasibilities (0003) --------------------------------------------------------


@pytest.fixture
def blue_feasibility(blue, connectors, providers):
    """Blue Mast has its own MTN connection, products and a finished run."""
    from apps.integrations.models import Connection, ProviderProduct
    from conftest import connect, rows, start_run

    owner = client_for(blue["owner"].user, blue["realm"])
    connect(
        owner,
        "mtn",
        "Blue MTN",
        api_key="invented-blue-key",
        requestor_email="ops@bluemast.example",
        customer_name="Blue",
    )
    products = list(ProviderProduct.objects.in_realm(blue["realm"]))
    run = start_run(
        owner, [p.id for p in products], rows(("Blue Depot", -25.7, 28.2)), name="Blue run"
    )
    return {
        "connection": Connection.objects.in_realm(blue["realm"]).get(),
        "products": products,
        "run_id": run.json()["id"],
        **blue,
    }


def _connection_snapshot(connection):
    connection.refresh_from_db()
    return (connection.name, connection.settings, connection.secrets_encrypted, connection.enabled)


def test_at_0003_25_another_companys_integrations_stay_out_of_sight(api, realm, blue_feasibility):
    theirs = blue_feasibility["connection"]
    before = _connection_snapshot(theirs)
    listed = api.get("/api/integrations/connections/")
    assert listed.json() == []
    assert "Blue" not in api.get("/api/feasibilities/runs/products/").content.decode()
    path = f"/api/integrations/connections/{theirs.id}/"
    attempts = [
        api.get(path),
        api.patch(path, {"name": "Mine now"}, format="json"),
        api.delete(path),
        api.post(f"{path}test/"),
        api.post(f"{path}sync/"),
        api.get(f"{path}products/"),
        api.get(f"{path}syncs/"),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    assert _connection_snapshot(theirs) == before
    missing = api.get("/api/integrations/connections/999999/")
    assert (attempts[0].status_code, attempts[0].json()) == (missing.status_code, missing.json())


def test_at_0003_25_another_companys_runs_stay_out_of_sight(api, realm, blue_feasibility):
    from apps.feasibilities.models import FeasibilityRun

    run_id = blue_feasibility["run_id"]
    before = FeasibilityRun.objects.in_realm(blue_feasibility["realm"]).get(pk=run_id).status
    assert api.get("/api/feasibilities/runs/").json() == []
    path = f"/api/feasibilities/runs/{run_id}/"
    attempts = [
        api.get(path),
        api.get(f"{path}sites/"),
        api.get(f"{path}sites/", {"ids": "1,2,3"}),
        api.get(f"{path}export/"),
        api.post(f"{path}cancel/"),
        api.post(f"{path}retry-failed/"),
        api.patch(path, {"name": "x"}, format="json"),
        api.delete(path),
    ]
    assert [r.status_code for r in attempts] == [404] * 6 + [405, 405]
    assert "Blue Depot" not in "".join(r.content.decode() for r in attempts)
    assert (
        FeasibilityRun.objects.in_realm(blue_feasibility["realm"]).get(pk=run_id).status == before
    )


def test_at_0003_26_a_run_cant_use_another_companys_products(
    api, realm, blue_feasibility, providers
):
    from apps.feasibilities.models import FeasibilityRun
    from conftest import rows, start_run

    sent = len(providers.mtn.feasibility_calls)
    theirs = [p.id for p in blue_feasibility["products"]]
    res = start_run(api, theirs, rows(("Mine", -26.1, 28.0)))
    assert res.status_code == 400 and "products" in res.json()
    assert FeasibilityRun.objects.in_realm(realm).count() == 0
    assert len(providers.mtn.feasibility_calls) == sent


def test_at_0003_27_tasks_stay_in_their_company(api, realm, blue_feasibility, providers):
    from apps.feasibilities import services
    from apps.feasibilities.models import FeasibilityResult, ProviderCheck
    from apps.integrations.models import ProviderProduct
    from conftest import connect, rows, start_run

    connect(
        api,
        "mtn",
        "My MTN",
        api_key="invented-mine-key",
        requestor_email="a@nw.example",
        customer_name="NW",
    )
    mine = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    providers.mtn.feasibility_calls.clear()
    run = start_run(api, mine, rows(("Mine", -26.1, 28.0))).json()
    (call,) = providers.mtn.feasibility_calls
    assert call["headers"]["x-api-key"] == "invented-mine-key"
    results = FeasibilityResult.objects.in_realm(realm)
    assert results.count() == 3 and {r.run_id for r in results} == {run["id"]}
    theirs = FeasibilityResult.objects.in_realm(blue_feasibility["realm"])
    assert {r.run_id for r in theirs} == {blue_feasibility["run_id"]}
    # A task naming the wrong company finds nothing to do.
    check = ProviderCheck.objects.in_realm(blue_feasibility["realm"]).first()
    assert services.perform_check(realm.id, check.id) == "skipped"
    assert services.plan_run(realm.id, blue_feasibility["run_id"]) == []


# --- the live socket follows the API's rules (AT-0003-12, AT-0003-13) ---------------------------


async def _live(user, realm_id):
    from channels.testing import WebsocketCommunicator
    from rest_framework_simplejwt.tokens import AccessToken

    from config.asgi import application

    communicator = WebsocketCommunicator(
        application, "/ws/events/", headers=[(b"origin", b"http://localhost:5184")]
    )
    connected, _ = await communicator.connect()
    assert connected
    token = str(AccessToken.for_user(user)) if user is not None else "not-a-token"
    await communicator.send_json_to({"type": "auth", "token": token, "realm": realm_id})
    return communicator, await communicator.receive_output(timeout=2)


async def _subscribe(socket, topic, subject=None):
    await socket.send_json_to({"type": "subscribe", "topic": topic, "subject": subject})
    return await socket.receive_json_from(timeout=2)


async def _event(realm_id, topic, subject=None, items=None):
    from channels.layers import get_channel_layer

    from apps.realms.events import group_name

    await get_channel_layer().group_send(
        group_name(realm_id),
        {
            "type": "realm.event",
            "realm": realm_id,
            "topic": topic,
            "subject": subject,
            "items": items,
            "has_items": items is not None,
        },
    )


@pytest.fixture
def fast_socket(monkeypatch):
    from apps.realms import consumers, listener

    monkeypatch.setattr(listener, "ensure_listening", lambda: None)
    monkeypatch.setattr(consumers, "FLUSH_SECONDS", 0.05)


def _two_companies_with_runs():
    """(me, my realm, my run id, my site ids, their realm, their run id) with Demo runs."""
    from apps.integrations.models import ProviderProduct
    from apps.integrations.services import load_definitions
    from apps.realms.services import add_member
    from conftest import connect, make_user, rows, start_run

    load_definitions()
    me = make_user("tester@example.com")
    mine = create_realm("Northwind Fibre")
    add_member(mine, me, ADMIN)
    owner = make_user("owner@example.com")
    theirs = create_realm("Blue Mast Telecom")
    add_member(theirs, owner, ADMIN)
    ids = {}
    for user, realm, name in [(me, mine, "Mine"), (owner, theirs, "Theirs")]:
        client = client_for(user, realm)
        connect(client, "demo", "Demo")
        products = list(ProviderProduct.objects.in_realm(realm).values_list("id", flat=True))
        ids[realm.id] = start_run(
            client, products, rows((name, -26.2, 28.1), (name + " 2", -26.3, 28.2))
        ).json()["id"]
    from apps.feasibilities.models import RunSite

    my_sites = list(RunSite.objects.in_realm(mine).values_list("id", flat=True))
    return me, mine, ids[mine.id], my_sites, theirs, ids[theirs.id]


@pytest.mark.django_db(transaction=True)
async def test_at_0003_12_the_live_socket_shows_only_what_the_api_would(fast_socket, settings):
    from asgiref.sync import sync_to_async

    settings.INTEGRATIONS_DEMO_ENABLED = True
    me, mine, run_id, sites, theirs, their_run = await sync_to_async(_two_companies_with_runs)()
    socket, ready = await _live(me, mine.id)
    assert json.loads(ready["text"]) == {"type": "ready", "realm": mine.id}

    assert await _subscribe(socket, "feasibility_run", run_id) == {
        "type": "subscribed",
        "topic": "feasibility_run",
        "subject": run_id,
    }
    # Another company's run is refused exactly like one that doesn't exist.
    refused_theirs = await _subscribe(socket, "feasibility_run", their_run)
    refused_missing = await _subscribe(socket, "feasibility_run", 999999)
    assert refused_theirs["type"] == refused_missing["type"] == "refused"
    assert await _subscribe(socket, "no_such_topic") == {
        "type": "refused",
        "topic": "no_such_topic",
        "subject": None,
    }

    # A finished line arrives with exactly what the API returns for it.
    await _event(mine.id, "feasibility_run", run_id, [sites[0]])
    message = await socket.receive_json_from(timeout=2)
    api_view = await sync_to_async(
        lambda: (
            client_for(me, mine)
            .get(f"/api/feasibilities/runs/{run_id}/sites/", {"ids": str(sites[0])})
            .json()
        )
    )()
    assert message["type"] == "data" and message["subject"] == run_id
    assert message["data"]["sites"] == api_view["results"]
    assert message["data"]["run"]["id"] == run_id

    # Events of the other company never reach this socket.
    await _event(theirs.id, "feasibility_run", their_run, [1])
    assert await socket.receive_nothing(timeout=0.2)
    await socket.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_at_0003_12_losing_access_stops_the_lines(fast_socket, settings):
    from asgiref.sync import sync_to_async

    settings.INTEGRATIONS_DEMO_ENABLED = True
    me, mine, run_id, sites, theirs, _ = await sync_to_async(_two_companies_with_runs)()

    # Without feasibilities.view: can't subscribe at all.
    custom = await sync_to_async(
        lambda: Role.objects.create(realm=mine, key="none", name="None", permissions=[])
    )()
    membership = await RealmMembership.objects.in_realm(mine).filter(user=me).afirst()
    admin_role = membership.role_id
    await RealmMembership.objects.in_realm(mine).filter(pk=membership.pk).aupdate(role=custom)
    socket, _ = await _live(me, mine.id)
    assert (await _subscribe(socket, "feasibility_run", run_id))["type"] == "refused"
    await socket.disconnect()

    # Lose it while watching: unsubscribed on the next event.
    await (
        RealmMembership.objects.in_realm(mine).filter(pk=membership.pk).aupdate(role_id=admin_role)
    )
    socket, _ = await _live(me, mine.id)
    assert (await _subscribe(socket, "feasibility_run", run_id))["type"] == "subscribed"
    await RealmMembership.objects.in_realm(mine).filter(pk=membership.pk).aupdate(role=custom)
    await _event(mine.id, "feasibility_run", run_id, [sites[0]])
    assert (await socket.receive_json_from(timeout=2))["type"] == "refused"
    await _event(mine.id, "feasibility_run", run_id, [sites[0]])
    assert await socket.receive_nothing(timeout=0.2)
    await socket.disconnect()

    # Removed from the company while watching: disconnected.
    await (
        RealmMembership.objects.in_realm(mine).filter(pk=membership.pk).aupdate(role_id=admin_role)
    )
    socket, _ = await _live(me, mine.id)
    await _subscribe(socket, "feasibility_run", run_id)
    await RealmMembership.objects.in_realm(mine).filter(pk=membership.pk).aupdate(status="removed")
    await _event(mine.id, "feasibility_run", run_id, [sites[0]])
    assert await socket.receive_output(timeout=2) == {"type": "websocket.close", "code": 4403}


@pytest.mark.django_db(transaction=True)
async def test_the_live_socket_refuses_outsiders(fast_socket):
    from asgiref.sync import sync_to_async

    from conftest import make_user

    me = await sync_to_async(make_user)("tester@example.com")
    mine = await sync_to_async(create_realm)("Northwind Fibre")
    theirs = await sync_to_async(create_realm)("Blue Mast Telecom")
    from apps.realms.services import add_member

    await sync_to_async(add_member)(mine, me, ADMIN)
    not_member = {"type": "websocket.close", "code": 4403}
    for realm_id in (theirs.id, 999999, "1 OR 1=1"):
        socket, reply = await _live(me, realm_id)
        assert reply == not_member
    socket, reply = await _live(None, mine.id)
    assert reply == {"type": "websocket.close", "code": 4401}


@pytest.mark.django_db(transaction=True)
async def test_at_0003_13_nothing_is_lost_if_the_connection_drops(fast_socket, settings):
    """While a tab is away, lines keep finishing; when it reconnects (and refetches through the
    API, as the portal does on "ready"), every finished line is there."""
    from asgiref.sync import sync_to_async

    settings.INTEGRATIONS_DEMO_ENABLED = True
    me, mine, run_id, sites, _, _ = await sync_to_async(_two_companies_with_runs)()
    socket, _ = await _live(me, mine.id)
    await _subscribe(socket, "feasibility_run", run_id)
    await socket.disconnect()
    await _event(mine.id, "feasibility_run", run_id, sites)  # nobody listening
    socket, ready = await _live(me, mine.id)
    assert json.loads(ready["text"])["type"] == "ready"
    fetched = await sync_to_async(
        lambda: client_for(me, mine).get(f"/api/feasibilities/runs/{run_id}/sites/").json()
    )()
    assert {s["id"] for s in fetched["results"] if s["state"] != "pending"} == set(sites)
    await socket.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_a_run_event_travels_through_postgres_to_the_socket(settings, monkeypatch):
    """The real path: services publish in one connection, the listener hears it in another."""
    import asyncio

    from asgiref.sync import sync_to_async

    from apps.realms import consumers, events, listener

    monkeypatch.setattr(consumers, "FLUSH_SECONDS", 0.05)
    settings.INTEGRATIONS_DEMO_ENABLED = True
    me, mine, run_id, sites, theirs, their_run = await sync_to_async(_two_companies_with_runs)()
    socket, _ = await _live(me, mine.id)
    try:
        await _subscribe(socket, "feasibility_run", run_id)
        await asyncio.sleep(0.5)  # let the listener connect and LISTEN
        await sync_to_async(events.publish)(theirs.id, "feasibility_run", their_run, [1])
        await sync_to_async(events.publish)(mine.id, "feasibility_run", run_id, sites[:1])
        message = await socket.receive_json_from(timeout=5)
        assert message["type"] == "data"
        assert [s["id"] for s in message["data"]["sites"]] == sites[:1]
        assert await socket.receive_nothing(timeout=0.3)
    finally:
        await socket.disconnect()
        task = listener.ensure_listening()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
