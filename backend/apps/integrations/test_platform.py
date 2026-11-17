"""Spec 0004: Telejects' provider accounts, shared with the companies staff choose."""

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.feasibilities.models import FeasibilityRun, ProviderCheck
from apps.feasibilities.services import runtime_for
from apps.integrations import services
from apps.integrations.models import (
    Connection,
    PlatformAccount,
    PlatformGrant,
    ProviderProduct,
    SyncRun,
)
from apps.realms.access_control import ADMIN
from apps.realms.services import create_realm
from conftest import client_for, connect, member, rows, start_run

pytestmark = pytest.mark.usefixtures("connectors")

PLATFORM_KEY = "invented-telejects-mtn-key"
OWN_KEY = "invented-northwind-mtn-key"
PLATFORM_EMAIL = "feasibility@telejects.example"


@pytest.fixture
def account(db, connectors):
    account = PlatformAccount(
        name="Telejects MTN",
        connector_key="mtn",
        settings={"requestor_email": PLATFORM_EMAIL, "customer_name": "Telejects"},
    )
    account.secrets = {"api_key": PLATFORM_KEY}
    account.save()
    return account


@pytest.fixture
def granted(realm, account, providers):
    services.grant_platform_account(realm, account)
    return Connection.objects.in_realm(realm).get()


def mtn_calls(providers):
    return [c["headers"]["x-api-key"] for c in providers.mtn.feasibility_calls]


def connection_json(api, connection):
    return api.get(f"/api/integrations/connections/{connection.id}/").json()


def test_at_0004_01_a_granted_company_is_connected_with_telejects_account(
    api, realm, granted, providers
):
    body = connection_json(api, granted)
    assert body["name"] == "MTN Business (Telejects account)"
    assert (body["credentials"], body["health"], body["product_count"]) == ("platform", "ok", 3)
    connectors = {c["key"]: c for c in api.get("/api/integrations/connectors/").json()}
    assert connectors["mtn"]["included"] is True and connectors["vodacom"]["included"] is False
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    run = start_run(api, products[:1], rows(("Depot", -26.1, 28.0))).json()
    assert FeasibilityRun.objects.in_realm(realm).get(pk=run["id"]).status == "completed"
    assert mtn_calls(providers) == [PLATFORM_KEY]


def test_at_0004_02_a_company_never_sees_telejects_credentials(api, realm, granted, providers):
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    run = start_run(api, products, rows(("Depot", -26.1, 28.0))).json()
    responses = [
        api.get("/api/integrations/connections/"),
        api.get(f"/api/integrations/connections/{granted.id}/"),
        api.get(f"/api/integrations/connections/{granted.id}/syncs/"),
        api.get(f"/api/integrations/connections/{granted.id}/products/"),
        api.get(f"/api/feasibilities/runs/{run['id']}/"),
        api.get(f"/api/feasibilities/runs/{run['id']}/sites/"),
        api.get(f"/api/feasibilities/runs/{run['id']}/export/"),
    ]
    for res in responses:
        text = res.content.decode()
        assert (
            PLATFORM_KEY not in text and PLATFORM_EMAIL not in text and "Telejects MTN" not in text
        )
    body = connection_json(api, granted)
    assert body["settings"] == {} and body["secrets_set"] == []
    # The recorded calls are redacted too.
    calls = json.dumps([c.calls for c in ProviderCheck.objects.in_realm(realm)])
    assert PLATFORM_KEY not in calls
    # And a platform connection's fields can't be edited.
    res = api.patch(
        f"/api/integrations/connections/{granted.id}/",
        {"fields": {"customer_name": "x"}},
        format="json",
    )
    assert res.status_code == 400


def test_at_0004_03_a_company_without_a_grant_cant_use_telejects_account(realm, account, providers):
    blue = create_realm("Blue Mast Telecom")
    owner = member(blue, "owner@example.com", ADMIN)
    client = client_for(owner.user, blue)
    connectors = {c["key"]: c for c in client.get("/api/integrations/connectors/").json()}
    assert connectors["mtn"]["included"] is False
    connect(
        client,
        "mtn",
        "Blue MTN",
        api_key="invented-blue-key",
        requestor_email="a@b.example",
        customer_name="B",
    )
    mine = Connection.objects.in_realm(blue).get()
    res = client.patch(
        f"/api/integrations/connections/{mine.id}/", {"credentials": "platform"}, format="json"
    )
    assert res.status_code == 400 and "credentials" in res.json()
    mine.refresh_from_db()
    assert mine.credentials == "own" and mine.secrets == {"api_key": "invented-blue-key"}


def test_at_0004_04_i_switch_to_our_own_account(api, realm, granted, providers):
    path = f"/api/integrations/connections/{granted.id}/"
    fields = {"api_key": OWN_KEY, "requestor_email": "ops@northwind.example", "customer_name": "NW"}
    res = api.patch(path, {"credentials": "own", "fields": fields}, format="json")
    assert res.status_code == 200
    body = res.json()
    assert (body["credentials"], body["secrets_set"]) == ("own", ["api_key"])
    granted.refresh_from_db()
    assert granted.platform_account is None and granted.secrets == {"api_key": OWN_KEY}
    syncs = SyncRun.objects.in_realm(realm).filter(connection=granted).recent()[:2]
    assert {s.credentials for s in syncs} == {"own"}
    providers.mtn.feasibility_calls.clear()
    products = [p.id for p in ProviderProduct.objects.in_realm(realm).current()]
    start_run(api, products[:1], rows(("Depot", -26.1, 28.0)))
    assert mtn_calls(providers) == [OWN_KEY]
    # Switching needs the fields the connector asks for.
    services.update_connection(granted, credentials="platform")
    missing = api.patch(path, {"credentials": "own", "fields": {"api_key": OWN_KEY}}, format="json")
    assert missing.status_code == 400 and "requestor_email" in missing.json()


def test_at_0004_05_i_switch_back_to_telejects_account(api, realm, granted, providers):
    path = f"/api/integrations/connections/{granted.id}/"
    fields = {"api_key": OWN_KEY, "requestor_email": "ops@northwind.example", "customer_name": "NW"}
    api.patch(path, {"credentials": "own", "fields": fields}, format="json")
    res = api.patch(path, {"credentials": "platform"}, format="json")
    assert res.status_code == 200 and res.json()["credentials"] == "platform"
    granted.refresh_from_db()
    assert granted.secrets == {} and granted.settings == {}
    assert granted.platform_account_id is not None
    assert res.json()["health"] == "ok"


def test_at_0004_06_withdrawing_a_grant_turns_the_connection_off(
    api, realm, account, granted, providers
):
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    run = start_run(api, products, rows(("Depot", -26.1, 28.0))).json()
    call_command("grant_platform_account", realm.id, account.id, "--withdraw")
    body = connection_json(api, granted)
    assert body["enabled"] is False
    assert (
        body["health_error"]
        == "Telejects' account for this provider isn't available to you any more."
    )
    assert api.get("/api/feasibilities/runs/products/").json() == []
    assert start_run(api, products, rows(("Depot", -26.1, 28.0))).status_code == 400
    assert (
        len(api.get(f"/api/feasibilities/runs/{run['id']}/sites/").json()["results"][0]["results"])
        == 3
    )
    # A check already queued for it fails instead of using the account.
    with pytest.raises(services.ConnectorError):
        services.connector_for(granted)
    # It can't be turned back on while the grant is gone; switching to our own is the way.
    res = api.patch(
        f"/api/integrations/connections/{granted.id}/", {"enabled": True}, format="json"
    )
    assert res.status_code == 400 and "enabled" in res.json()
    # Granting again turns it back on.
    call_command("grant_platform_account", realm.id, account.id)
    assert connection_json(api, granted)["enabled"] is True


def test_at_0004_07_a_company_that_already_has_its_own_account_keeps_it(
    api, realm, account, providers
):
    connect(
        api,
        "mtn",
        "Our MTN",
        api_key=OWN_KEY,
        requestor_email="ops@northwind.example",
        customer_name="NW",
    )
    services.grant_platform_account(realm, account)
    (connection,) = Connection.objects.in_realm(realm)
    assert connection.credentials == "own" and connection.secrets == {"api_key": OWN_KEY}
    assert connection_json(api, connection)["can_use_platform"] is True


def test_at_0004_08_companies_on_one_account_share_its_limits(
    api, realm, account, granted, providers
):
    blue = create_realm("Blue Mast Telecom")
    services.grant_platform_account(blue, account)
    owner = client_for(member(blue, "owner@example.com", ADMIN).user, blue)
    connect(owner, "vodacom", "Blue Vodacom", auth_key="invented-voda", calling_system="Blue")
    keys = set()
    for company, client in [(realm, api), (blue, owner)]:
        products = [p.id for p in ProviderProduct.objects.in_realm(company)]
        run = start_run(client, products, rows(("Site", -26.1, 28.0))).json()
        checks = ProviderCheck.objects.in_realm(company).of_run(run["id"])
        keys |= {
            key
            for key, _, _ in runtime_for(
                company.id, list(checks.values_list("id", flat=True))
            ).values()
        }
    voda = Connection.objects.in_realm(blue).get(connector_key="vodacom")
    assert keys == {f"platform-{account.id}", f"connection-{voda.id}"}


def test_at_0004_09_a_failing_telejects_account_shows_everywhere(
    api, realm, account, granted, providers
):
    blue = create_realm("Blue Mast Telecom")
    services.grant_platform_account(blue, account)
    owner = client_for(member(blue, "owner@example.com", ADMIN).user, blue)
    green = create_realm("Green Line")
    green_client = client_for(member(green, "green@example.com", ADMIN).user, green)
    connect(
        green_client,
        "mtn",
        "Green MTN",
        api_key="invented-green",
        requestor_email="g@g.example",
        customer_name="G",
    )
    providers.mtn.status = 401
    assert services.due_platform_checks(now=timezone.now() + timedelta(hours=7)) == [account.id]
    assert services.test_platform_account(account.id) is False
    message = "Telejects' account for this provider is failing; we're on it."
    for client in (api, owner):
        (body,) = client.get("/api/integrations/connections/").json()
        assert (body["health"], body["health_error"]) == ("failing", message)
    account.refresh_from_db()
    assert account.health == "failing" and "refused" in account.health_error
    assert green_client.get("/api/integrations/connections/").json()[0]["health"] == "ok"
    # Scheduled credential checks of platform connections are the account's, once, not per
    # company; their product syncs stay per company.
    due = services.due_operations(now=timezone.now() + timedelta(hours=25))
    assert (realm.id, granted.id, "test_connection") not in due
    assert (realm.id, granted.id, "sync_products") in due


def test_at_0004_10_every_call_says_whose_credentials_it_used(
    api, realm, account, granted, providers
):
    connect(api, "vodacom", "Vodacom", auth_key="invented-voda", calling_system="NW")
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    run = start_run(api, products, rows(("Depot", -26.1, 28.0))).json()
    used = {
        (c.connection.connector_key, c.credentials, c.platform_account_id)
        for c in ProviderCheck.objects.in_realm(realm)
        .of_run(run["id"])
        .select_related("connection")
    }
    assert used == {("mtn", "platform", account.id), ("vodacom", "own", None)}


def test_at_0004_11_only_admins_switch_and_only_staff_grant(
    api, realm, account, granted, providers
):
    pm = client_for(member(realm, "pm@example.com", "project_manager").user, realm)
    res = pm.patch(
        f"/api/integrations/connections/{granted.id}/", {"credentials": "own"}, format="json"
    )
    assert res.status_code == 403
    # There is no grant endpoint at all: only Django admin and manage.py.
    from django.urls import get_resolver

    names = {str(p.pattern) for p in get_resolver().url_patterns}
    assert not any("grant" in name for name in names)
    assert (
        api.post("/api/integrations/grants/", {"account": account.id}, format="json").status_code
        == 404
    )


def test_at_0004_12_companies_stay_apart_on_a_shared_account(
    api, realm, account, granted, providers
):
    blue = create_realm("Blue Mast Telecom")
    services.grant_platform_account(blue, account)
    owner = client_for(member(blue, "owner@example.com", ADMIN).user, blue)
    for client, name in [(api, "Northwind Depot"), (owner, "Blue Depot")]:
        products = [p["id"] for p in client.get("/api/feasibilities/runs/products/").json()]
        start_run(client, products, rows((name, -26.1, 28.0)), name=name)
    mine = api.get("/api/feasibilities/runs/").json()
    assert [r["name"] for r in mine] == ["Northwind Depot"]
    blue_conn = Connection.objects.in_realm(blue).get()
    assert api.get(f"/api/integrations/connections/{blue_conn.id}/").status_code == 404
    assert api.get(f"/api/integrations/connections/{blue_conn.id}/syncs/").status_code == 404
    assert len(api.get("/api/integrations/connections/").json()) == 1
    assert PlatformGrant.objects.in_realm(realm).count() == 1
    assert "Blue" not in api.get("/api/integrations/connectors/").content.decode()


def test_the_database_refuses_a_platform_connection_without_an_account(realm):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        Connection.objects.create(
            realm=realm, name="Broken", connector_key="mtn", credentials="platform"
        )


def test_the_admin_keeps_platform_secrets_write_only(admin_client, account):
    res = admin_client.get(f"/admin/integrations/platformaccount/{account.id}/change/")
    assert res.status_code == 200
    assert PLATFORM_KEY not in res.content.decode()
    assert "api_key" in res.content.decode()  # which secrets are saved, not their values
