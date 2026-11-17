"""Spec 0005: integration request logs."""

import json

import pytest

from apps.integration_logs import services
from apps.integration_logs.models import IntegrationLog, LogRetention
from apps.integrations.models import Connection, PlatformAccount, ProviderProduct
from apps.integrations.services import grant_platform_account
from apps.realms.access_control import ADMIN
from apps.realms.models import RealmMembership, Role
from apps.realms.services import create_realm
from conftest import client_for, connect, member, rows, start_run

pytestmark = pytest.mark.usefixtures("connectors")

MTN_KEY = "invented-mtn-log-key"
VODA_KEY = "invented-voda-log-key"
SITES = [("Depot", -26.1, 28.0), ("Store 2", -33.9, 18.4)]


@pytest.fixture
def both(api, realm, providers):
    connect(
        api, "mtn", "MTN", api_key=MTN_KEY, requestor_email="ops@nw.example", customer_name="NW"
    )
    connect(api, "vodacom", "Vodacom", auth_key=VODA_KEY, calling_system="Northwind")
    return {p.name: p.id for p in ProviderProduct.objects.in_realm(realm)}


def logs(client, **params):
    return client.get("/api/integration-logs/", params).json()


def test_at_0005_01_every_provider_request_is_logged(api, realm, both):
    run = start_run(api, [both["Business LTE"], both["Business Fibre"]], rows(*SITES)).json()
    entries = logs(api)["results"]
    operations = [e["operation"] for e in entries]
    # Connecting each: a test and a product sync (Vodacom tests with a feasibility call).
    assert operations.count("sync_products") >= 2
    assert operations.count("test_connection") >= 1
    checks = [
        e for e in entries if e["operation"] == "check_feasibility" and e["run_id"] == run["id"]
    ]
    # MTN takes both sites in one call; Vodacom one per site.
    assert len(checks) == 3
    detail = api.get(f"/api/integration-logs/{checks[0]['id']}/").json()
    assert detail["method"] == "POST" and detail["status_code"] == 200
    assert detail["request_body"] and detail["response_body"] and detail["duration_ms"] is not None
    assert detail["outcome"] == "ok" and detail["connection_name"] in {"MTN", "Vodacom"}


def test_at_0005_02_failed_requests_are_logged_with_each_retry(api, realm, both, providers):
    providers.vodacom.down.add("-33.9")
    start_run(api, [both["Business Fibre"]], rows(*SITES))
    failed = logs(api, outcome="error")["results"]
    assert [e["attempt"] for e in failed] == [3, 2, 1]
    assert {(e["status_code"], e["outcome"]) for e in failed} == {(503, "provider_down")}
    assert (
        "Service unavailable"
        in api.get(f"/api/integration-logs/{failed[0]['id']}/").json()["response_body"]
    )


def test_at_0005_02_timeouts_and_non_json_are_logged(api, realm, both, providers):
    providers.vodacom.slow.add("-26.1")
    providers.mtn.not_json = True
    start_run(api, [both["Business LTE"], both["Business Fibre"]], rows(SITES[0]))
    errors = {e["outcome"] for e in logs(api, outcome="error")["results"]}
    assert {"timeout", "bad_response"} <= errors
    bad = logs(api, outcome="bad_response")["results"][0]
    assert "not json" in api.get(f"/api/integration-logs/{bad['id']}/").json()["response_body"]
    slow = logs(api, outcome="timeout")["results"][0]
    assert slow["status_code"] is None and slow["error"]


def test_at_0005_03_logs_never_show_a_secret(api, realm, both, settings):
    settings.INTEGRATIONS_PLATFORM_ACCOUNTS = {
        "demo": {"secrets": {}, "settings": {"account_name": "telejects-internal-account"}}
    }
    account = PlatformAccount.objects.create(
        name="Telejects Demo", connector_key="demo", env_key="demo", available_to_all=False
    )
    grant_platform_account(realm, account)
    products = [p.id for p in ProviderProduct.objects.in_realm(realm)]
    start_run(api, products, rows(*SITES))
    everything = json.dumps(list(IntegrationLog.objects.in_realm(realm).values()), default=str)
    for secret in (MTN_KEY, VODA_KEY, "telejects-internal-account"):
        assert secret not in everything
        assert logs(api, search=secret)["count"] == 0
    mtn = logs(api, connection=Connection.objects.in_realm(realm).get(name="MTN").id)["results"][0]
    detail = api.get(f"/api/integration-logs/{mtn['id']}/").json()
    assert detail["request_headers"]["X-API-KEY"] == "[redacted]"


def test_at_0005_04_i_find_the_request_im_looking_for(api, realm, both, providers):
    providers.vodacom.down.add("-33.9")
    run = start_run(api, [both["Business LTE"], both["Business Fibre"]], rows(*SITES)).json()
    voda = Connection.objects.in_realm(realm).get(name="Vodacom").id
    by_connection = logs(api, connection=voda)["results"]
    assert by_connection and {e["connection_name"] for e in by_connection} == {"Vodacom"}
    assert {e["status_code"] for e in logs(api, status="5xx")["results"]} == {503}
    assert all(e["status_code"] == 200 for e in logs(api, status="2xx")["results"])
    assert {e["operation"] for e in logs(api, operation="sync_products")["results"]} == {
        "sync_products"
    }
    assert {e["run_id"] for e in logs(api, run=run["id"])["results"]} == {run["id"]}
    assert logs(api, search="-33.9")["count"] >= 1
    assert logs(api, search="nothing-like-this")["count"] == 0
    assert logs(api, **{"from": "2999-01-01"})["count"] == 0
    newest = logs(api)["results"]
    assert [e["id"] for e in newest] == sorted((e["id"] for e in newest), reverse=True)


def test_at_0005_05_i_see_the_whole_exchange(api, realm, both):
    start_run(api, [both["Business Fibre"]], rows(SITES[0]))
    entry = logs(api, operation="check_feasibility")["results"][0]
    detail = api.get(f"/api/integration-logs/{entry['id']}/").json()
    assert detail["url"].endswith("/api/ProductFeasible")
    assert json.loads(detail["request_body"])["productIds"] == [10]
    assert "accessMediums" in detail["response_body"]
    assert detail["response_headers"] and detail["definition_version"] == 1
    assert detail["run_id"] and detail["check_id"]


def test_at_0005_06_a_company_keeps_its_limit_of_requests(api, realm, both, settings):
    settings.INTEGRATION_LOGS_DEFAULT_LIMIT = 5
    blue = create_realm("Blue Mast Telecom")
    owner = client_for(member(blue, "owner@example.com", ADMIN).user, blue)
    connect(owner, "demo", "Demo")
    theirs = IntegrationLog.objects.in_realm(blue).count()
    start_run(
        api, [both["Business Fibre"]], rows(*[(f"S{i}", -26 - i / 100, 28) for i in range(8)])
    )
    kept = list(IntegrationLog.objects.in_realm(realm).newest().values_list("id", flat=True))
    assert len(kept) == 5
    assert IntegrationLog.objects.in_realm(blue).count() == theirs
    # The newest stay.
    assert kept == sorted(kept, reverse=True) and kept[0] == logs(api)["results"][0]["id"]


def test_at_0005_06_the_default_comes_from_settings(settings):
    from django.apps import apps

    assert (
        apps.get_app_config("integration_logs").default_limit
        == settings.INTEGRATION_LOGS_DEFAULT_LIMIT
    )


def test_at_0005_07_i_can_see_the_limit(api, realm, both):
    body = api.get("/api/integration-logs/limits/").json()
    assert body["max_entries"] == body["default"] == services.default_limit()
    assert body["kept"] == IntegrationLog.objects.in_realm(realm).count()


def test_at_0005_08_staff_change_a_companys_limit(api, realm, both, admin_client):
    blue = create_realm("Blue Mast Telecom")
    res = admin_client.post(
        "/admin/integration_logs/logretention/add/", {"realm": realm.id, "max_entries": 3}
    )
    assert res.status_code == 302
    assert IntegrationLog.objects.in_realm(realm).count() == 3
    assert api.get("/api/integration-logs/limits/").json()["max_entries"] == 3
    assert services.limit_for(blue.id) == services.default_limit()
    services.set_limit(realm.id, 1000)
    assert api.get("/api/integration-logs/limits/").json()["max_entries"] == 1000
    assert LogRetention.objects.in_realm(realm).get().max_entries == 1000


def test_at_0005_09_new_requests_are_announced(api, realm, both, monkeypatch):
    from apps.realms import events

    published = []
    monkeypatch.setattr(events, "publish", lambda *a, **k: published.append((a, k)))
    start_run(api, [both["Business Fibre"]], rows(SITES[0]))
    announced = [k["items"] for a, k in published if a[1] == "integration_logs"]
    assert announced and all(len(items) == 1 for items in announced)
    from apps.integration_logs.live import _render

    membership = RealmMembership.objects.in_realm(realm).get()
    rendered = _render(membership, None, announced[-1])
    assert rendered["entries"][0]["id"] == announced[-1][0]


def test_at_0005_10_from_a_provider_error_to_its_request(api, realm, both, providers):
    providers.vodacom.down.add("-33.9")
    run = start_run(api, [both["Business Fibre"]], rows(*SITES)).json()
    site = next(
        s
        for s in api.get(f"/api/feasibilities/runs/{run['id']}/sites/").json()["results"]
        if s["errors"]
    )
    log_id = site["errors"][0]["log"]
    entry = api.get(f"/api/integration-logs/{log_id}/").json()
    assert entry["outcome"] == "provider_down" and entry["attempt"] == 3
    # A sync links to its entry too.
    voda = Connection.objects.in_realm(realm).get(name="Vodacom")
    sync = api.get(f"/api/integrations/connections/{voda.id}/syncs/").json()[0]
    assert sync["log"] and api.get(f"/api/integration-logs/{sync['log']}/").status_code == 200


def test_at_0005_11_only_people_with_the_permission_see_logs(api, realm, both):
    viewer = client_for(member(realm, "viewer@example.com", "viewer").user, realm)
    entry = logs(api)["results"][0]
    assert viewer.get("/api/integration-logs/").status_code == 403
    assert viewer.get(f"/api/integration-logs/{entry['id']}/").status_code == 403
    assert viewer.get("/api/integration-logs/limits/").status_code == 403
    pm = client_for(member(realm, "pm@example.com", "project_manager").user, realm)
    assert pm.get("/api/integration-logs/").status_code == 200
    role = Role.objects.create(
        realm=realm, key="no-logs", name="No logs", permissions=["integrations.view"]
    )
    RealmMembership.objects.in_realm(realm).filter(user__email="pm@example.com").update(role=role)
    assert pm.get("/api/integration-logs/").status_code == 403


def test_the_log_is_read_only(api, realm, both):
    entry = logs(api)["results"][0]
    assert api.post("/api/integration-logs/", {}, format="json").status_code == 405
    assert api.delete(f"/api/integration-logs/{entry['id']}/").status_code == 405
    assert api.patch(f"/api/integration-logs/{entry['id']}/", {}, format="json").status_code == 405


def test_bodies_are_capped_at_256_kb(realm):
    from apps.integrations.canonical import CallRecord

    recorder = services.Recorder(realm_id=realm.id, operation="sync_products")
    recorder(
        CallRecord(
            request={"method": "GET", "url": "https://x.example"},
            response="x" * 400_000,
            status_code=200,
        )
    )
    body = IntegrationLog.objects.in_realm(realm).get().response_body
    assert len(body.encode()) < 256 * 1024 + 100 and "truncated (390 KB in all)" in body


def test_a_logging_failure_never_breaks_the_call(api, realm, both, monkeypatch):
    from apps.integration_logs.models import IntegrationLog as Model

    def broken(*args, **kwargs):
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(Model, "save", broken)
    run = start_run(api, [both["Business Fibre"]], rows(SITES[0])).json()
    assert api.get(f"/api/feasibilities/runs/{run['id']}/").json()["status"] == "completed"
