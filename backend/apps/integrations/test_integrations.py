"""Spec 0003, Integrations: connecting providers with the company's own accounts."""

import json
import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.integrations import services
from apps.integrations.admin import DefinitionForm
from apps.integrations.models import Connection, ProviderProduct, SyncRun
from apps.integrations.spec import ConnectorSpec
from apps.integrations.test_engine import PRESENCE
from conftest import client_for, connect, member

pytestmark = pytest.mark.usefixtures("connectors")

KEY = "invented-mtn-key-0001"
MTN_FIELDS = {"api_key": KEY, "requestor_email": "ops@northwind.example", "customer_name": "NW"}


def connected_mtn(api, providers, **overrides):
    res = connect(api, "mtn", "MTN main", **{**MTN_FIELDS, **overrides})
    assert res.status_code == 201, res.content
    return res.json()


def test_at_0003_01_i_see_the_providers_i_can_connect(api, providers):
    connectors = api.get("/api/integrations/connectors/").json()
    assert {c["key"] for c in connectors} == {"demo", "herotel", "link_africa", "mtn", "vodacom"}
    mtn = next(c for c in connectors if c["key"] == "mtn")
    assert mtn["name"] == "MTN Business" and mtn["description"]
    assert [(f["key"], f["type"]) for f in mtn["fields"]] == [
        ("api_key", "secret"),
        ("requestor_email", "email"),
        ("customer_name", "text"),
    ]
    connected_mtn(api, providers)
    listed = api.get("/api/integrations/connections/").json()
    assert [(c["name"], c["connector_name"], c["health"]) for c in listed] == [
        ("MTN main", "MTN Business", "ok")
    ]


def test_at_0003_01_demo_is_offered_only_where_enabled(api, settings):
    settings.INTEGRATIONS_DEMO_ENABLED = False
    assert "demo" not in {c["key"] for c in api.get("/api/integrations/connectors/").json()}
    assert connect(api, "demo").status_code == 400


def test_at_0003_02_i_connect_a_provider_by_filling_in_what_it_asks_for(api, providers):
    body = connected_mtn(api, providers)
    assert body["settings"] == {"requestor_email": "ops@northwind.example", "customer_name": "NW"}
    connection = api.get(f"/api/integrations/connections/{body['id']}/").json()
    assert connection["health"] == "ok"
    assert connection["product_count"] == 3
    products = api.get(f"/api/integrations/connections/{body['id']}/products/").json()
    assert {(p["name"], p["product_type_label"]) for p in products} == {
        ("Business Fibre 100", "Fibre"),
        ("Business Wireless 20", "Fixed wireless"),
        ("Business LTE", "LTE"),
    }
    syncs = api.get(f"/api/integrations/connections/{body['id']}/syncs/").json()
    assert [(s["kind"], s["outcome"], s["added"]) for s in syncs] == [
        ("sync_products", "ok", 3),
        ("test_connection", "ok", 0),
    ]


def test_at_0003_02_what_a_connector_asks_for_is_checked(api, providers):
    res = connect(api, "mtn", "MTN", api_key="", requestor_email="not-an-email", customer_name="")
    assert res.status_code == 400
    assert set(res.json()) == {"api_key", "requestor_email", "customer_name"}
    res = connect(api, "mtn", "MTN", **MTN_FIELDS, extra="x")
    assert res.status_code == 400 and "fields" in res.json()
    connected_mtn(api, providers)
    again = connect(api, "mtn", "mtn MAIN", **MTN_FIELDS)
    assert again.status_code == 400 and "name" in again.json()


def test_at_0003_03_wrong_credentials_are_caught_when_i_connect(api, providers):
    providers.mtn.status = 401
    body = connected_mtn(api, providers)
    connection = api.get(f"/api/integrations/connections/{body['id']}/").json()
    assert connection["health"] == "failing"
    assert connection["health_error"] == "The provider refused this connection's credentials."
    assert connection["product_count"] == 0
    kinds = [
        s["kind"] for s in api.get(f"/api/integrations/connections/{body['id']}/syncs/").json()
    ]
    assert kinds == ["test_connection"]


def test_at_0003_04_secrets_never_come_back(api, realm, providers, caplog):
    caplog.set_level(logging.DEBUG)
    body = connected_mtn(api, providers)
    path = f"/api/integrations/connections/{body['id']}/"
    responses = [
        api.get("/api/integrations/connections/"),
        api.get(path),
        api.get(f"{path}syncs/"),
        api.get(f"{path}products/"),
    ]
    for res in responses:
        assert KEY not in res.content.decode()
    assert api.get(path).json()["secrets_set"] == ["api_key"]
    stored = Connection.objects.in_realm(realm).get()
    assert KEY not in stored.secrets_encrypted and stored.secrets == {"api_key": KEY}
    assert KEY not in caplog.text

    # Empty keeps the old key; a new one replaces it.
    assert (
        api.patch(
            path, {"fields": {"api_key": "", "customer_name": "NW2"}}, format="json"
        ).status_code
        == 200
    )
    stored.refresh_from_db()
    assert stored.secrets == {"api_key": KEY} and stored.settings["customer_name"] == "NW2"
    api.patch(path, {"fields": {"api_key": "invented-mtn-key-0002"}}, format="json")
    stored.refresh_from_db()
    assert stored.secrets == {"api_key": "invented-mtn-key-0002"}
    # Changing the credentials tests them again.
    assert providers.mtn.feasibility_calls == []
    assert SyncRun.objects.in_realm(realm).filter(kind="test_connection").count() == 3


def test_at_0003_05_products_are_kept_fresh(api, realm, providers):
    body = connected_mtn(api, providers)
    connection = Connection.objects.in_realm(realm).get(pk=body["id"])
    assert services.due_operations() == []
    later = timezone.now() + timedelta(hours=25)
    due = services.due_operations(now=later)
    assert (realm.id, connection.id, "sync_products") in due

    providers.mtn.products = ["Business Fibre 100", "Business Fibre 1000", "Business LTE"]
    services.run_operation(realm.id, connection.id, "sync_products", "scheduled")
    products = {p.name: p for p in ProviderProduct.objects.in_realm(realm)}
    assert products["Business Fibre 1000"].retired_at is None
    assert products["Business Wireless 20"].retired_at is not None
    pickable = api.get("/api/feasibilities/runs/products/").json()
    assert "Business Wireless 20" not in {p["name"] for p in pickable}
    last = api.get(f"/api/integrations/connections/{connection.id}/syncs/").json()[0]
    assert (last["trigger"], last["added"], last["retired"]) == ("scheduled", 1, 1)

    # It comes back if the provider offers it again.
    providers.mtn.products = ["Business Wireless 20"]
    services.run_operation(realm.id, connection.id, "sync_products", "scheduled")
    assert (
        ProviderProduct.objects.in_realm(realm).get(name="Business Wireless 20").retired_at is None
    )


def test_at_0003_06_a_failing_connection_is_flagged(api, realm, providers):
    body = connected_mtn(api, providers)
    providers.mtn.status = 403
    services.run_operation(realm.id, body["id"], "test_connection", "scheduled")
    listed = api.get("/api/integrations/connections/").json()[0]
    assert listed["health"] == "failing"
    assert "refused" in listed["health_error"]
    # A provider outage isn't blamed on the credentials.
    providers.mtn.status = 200
    services.run_operation(realm.id, body["id"], "test_connection", "manual")
    providers.mtn.status = 503
    services.run_operation(realm.id, body["id"], "test_connection", "scheduled")
    listed = api.get("/api/integrations/connections/").json()[0]
    assert listed["health"] == "ok" and "unavailable" in listed["health_error"]


def test_at_0003_07_only_admins_manage_integrations(api, realm, providers):
    body = connected_mtn(api, providers)
    path = f"/api/integrations/connections/{body['id']}/"
    pm = client_for(member(realm, "pm@example.com", "project_manager").user, realm)
    assert pm.get("/api/integrations/connectors/").status_code == 200
    assert pm.get(path).status_code == 200
    assert pm.get(f"{path}products/").status_code == 200
    attempts = [
        connect(pm, "mtn", "Other", **MTN_FIELDS),
        pm.patch(path, {"name": "Changed"}, format="json"),
        pm.post(f"{path}test/"),
        pm.post(f"{path}sync/"),
        pm.delete(path),
    ]
    assert [r.status_code for r in attempts] == [403] * 5
    assert Connection.objects.in_realm(realm).get().name == "MTN main"
    viewer = client_for(member(realm, "viewer@example.com", "viewer").user, realm)
    assert viewer.get("/api/integrations/connections/").status_code == 403
    assert viewer.get("/api/integrations/connectors/").status_code == 403


def test_at_0003_08_a_new_connector_needs_no_code(api, realm):
    import httpx
    import respx

    assert services.save_definition(ConnectorSpec.model_validate(PRESENCE))[2] is True
    assert "presence" in {c["key"] for c in api.get("/api/integrations/connectors/").json()}
    with respx.mock() as router:
        router.get("https://coverage.example.com/check").mock(
            return_value=httpx.Response(200, json={"keys": ["onnet"]})
        )
        res = connect(api, "presence", "Coverage", api_key="invented-presence-key")
    assert res.status_code == 201
    assert api.get(f"/api/integrations/connections/{res.json()['id']}/").json()["health"] == "ok"
    assert ProviderProduct.objects.in_realm(realm).count() == 2

    # Saving the same definition again changes nothing; a changed one is a new version.
    assert services.save_definition(ConnectorSpec.model_validate(PRESENCE))[1:] == (1, False)
    changed = {**PRESENCE, "name": "Presence Provider 2"}
    assert services.save_definition(ConnectorSpec.model_validate(changed))[1:] == (2, True)


def test_at_0003_08_an_invalid_definition_is_refused_with_whats_wrong():
    form = DefinitionForm(
        data={
            "key": "bad",
            "version": 1,
            "spec": json.dumps({**PRESENCE, "key": "bad", "base_url": "ftp://x"}),
            "published": True,
        }
    )
    assert not form.is_valid()
    assert "https://" in str(form.errors["spec"])


def test_removing_a_used_connection_turns_it_off(api, realm, providers):
    body = connected_mtn(api, providers)
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    from conftest import rows, start_run

    assert start_run(api, products[:1], rows(("Depot", -26.1, 28.0))).status_code == 201
    res = api.delete(f"/api/integrations/connections/{body['id']}/")
    assert res.json()["deleted"] is False
    assert Connection.objects.in_realm(realm).get().enabled is False
    other = connect(api, "demo", "Demo")
    assert api.delete(f"/api/integrations/connections/{other.json()['id']}/").status_code == 204
