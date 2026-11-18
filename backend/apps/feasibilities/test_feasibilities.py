"""Spec 0003, bulk feasibility runs."""

import csv
import io
import json
from decimal import Decimal

import pytest

from apps.feasibilities import services
from apps.feasibilities.models import FeasibilityResult, FeasibilityRun, ProviderCheck
from apps.integrations.connectors import demo
from apps.integrations.models import Connection, ProviderProduct
from apps.realms.models import RealmMembership, Role
from conftest import client_for, connect, member, rows, start_run

pytestmark = pytest.mark.usefixtures("connectors")

MTN_KEY = "invented-mtn-key-0001"


@pytest.fixture
def mtn_and_vodacom(api, realm, providers):
    connect(
        api,
        "mtn",
        "MTN",
        api_key=MTN_KEY,
        requestor_email="ops@northwind.example",
        customer_name="NW",
    )
    connect(api, "vodacom", "Vodacom", auth_key="invented-voda-key", calling_system="Northwind")
    products = {p.name: p for p in ProviderProduct.objects.in_realm(realm)}
    # Connecting tests the credentials; count only what runs send.
    providers.mtn.feasibility_calls.clear()
    providers.vodacom.feasibility_calls.clear()
    return products


def picks(products, *names):
    return [products[n].id for n in names]


def sites_of(api, run_id, **params):
    return api.get(f"/api/feasibilities/runs/{run_id}/sites/", params).json()["results"]


def run_of(api, run_id):
    return api.get(f"/api/feasibilities/runs/{run_id}/").json()


SITES = [("Depot", -26.1, 28.0), ("Store 2", -33.9, 18.4), ("Store 3", -29.85, 31.02)]


# --- running ------------------------------------------------------------------------------------


def test_at_0003_09_i_check_a_list_of_sites(api, mtn_and_vodacom, providers):
    providers.mtn.not_feasible.add("-33.9")
    chosen = picks(mtn_and_vodacom, "Business Fibre 100", "Business Fibre")
    res = start_run(api, chosen, rows(*SITES))
    assert res.status_code == 201, res.content
    run = run_of(api, res.json()["id"])
    assert run["status"] == "completed"
    assert (run["site_count"], run["sites_finished"]) == (3, 3)
    sites = sites_of(api, run["id"])
    assert [s["name"] for s in sites] == ["Depot", "Store 2", "Store 3"]
    depot = {(r["product"], r["variant_name"]): r["status_label"] for r in sites[0]["results"]}
    mtn_fibre, voda_fibre = chosen
    assert depot == {
        (mtn_fibre, ""): "Available",
        (voda_fibre, "Fibre"): "Available",
        (voda_fibre, "Fixed Wireless"): "Coverage only",
    }
    # Only what can be delivered is kept: MTN said no at Store 2, so there's no MTN row, and the
    # answered site reads as Not available (in the portal and the export).
    assert mtn_fibre not in {r["product"] for r in sites[1]["results"]}
    assert all(s["state"] == "done" for s in sites)
    export = api.get(f"/api/feasibilities/runs/{run['id']}/export/").content.decode()
    assert "Store 2" in export and "Not available" in export


def test_at_0003_10_bad_rows_are_shown_before_i_start(api, mtn_and_vodacom):
    assert services.row_problems({"name": "", "latitude": "abc", "longitude": 200}) == [
        "No name.",
        "The latitude isn't a number from -90 to 90.",
        "The longitude isn't a number from -180 to 180.",
    ]
    bad = rows(("Depot", -26.1, 28.0), ("", -95, 28.0), ("Store", "x", 28.0))
    res = start_run(api, picks(mtn_and_vodacom, "Business LTE"), bad)
    assert res.status_code == 400
    assert set(res.json()["rows"]) == {"3", "4"}
    assert "The latitude isn't a number from -90 to 90." in res.json()["rows"]["3"]
    assert FeasibilityRun.objects.in_realm(mtn_and_vodacom["Business LTE"].realm_id).count() == 0


def test_a_run_needs_a_name_products_and_sites(api, mtn_and_vodacom):
    lte = picks(mtn_and_vodacom, "Business LTE")
    assert start_run(api, [], rows(*SITES)).status_code == 400
    assert start_run(api, lte, []).status_code == 400
    assert start_run(api, lte, rows(*SITES), name="").status_code == 400


def test_a_queued_runs_sites_are_pending(api, mtn_and_vodacom, monkeypatch):
    monkeypatch.setattr(services, "_after_commit", lambda func: None)
    run = start_run(api, picks(mtn_and_vodacom, "Business LTE"), rows(*SITES)).json()
    assert run_of(api, run["id"])["status"] == "queued"
    assert [s["state"] for s in sites_of(api, run["id"])] == ["pending"] * 3
    api.post(f"/api/feasibilities/runs/{run['id']}/cancel/")
    assert [s["state"] for s in sites_of(api, run["id"])] == ["cancelled"] * 3


def test_at_0003_11_i_see_each_lines_results_as_it_finishes(
    api, realm, mtn_and_vodacom, worker, monkeypatch
):
    from apps.realms import events

    published = []
    monkeypatch.setattr(events, "publish", lambda *a, **k: published.append((a, k)))
    worker.hold()
    run = start_run(api, picks(mtn_and_vodacom, "Business Fibre"), rows(*SITES)).json()
    sites = sites_of(api, run["id"])
    assert [s["state"] for s in sites] == ["pending"] * 3
    assert all(s["results"] == [] for s in sites)

    published.clear()
    first = worker.planned[0]
    services.perform_check(realm.id, first)
    after = sites_of(api, run["id"])
    assert [s["state"] for s in after] == ["done", "pending", "pending"]
    assert after[0]["results"]
    assert run_of(api, run["id"])["sites_finished"] == 1
    # Open tabs are told which lines changed (ids only).
    events_for_run = [k for a, k in published if a[1] == "feasibility_run"]
    assert events_for_run == [{"subject": run["id"], "items": [after[0]["id"]]}]

    for check_id in worker.planned[1:]:
        services.perform_check(realm.id, check_id)
    assert run_of(api, run["id"])["status"] == "completed"


def test_at_0003_14_one_provider_failing_doesnt_stop_the_run(api, mtn_and_vodacom, providers):
    providers.vodacom.down.add("-33.9")
    chosen = picks(mtn_and_vodacom, "Business Fibre 100", "Business Fibre")
    run = start_run(api, chosen, rows(*SITES)).json()
    assert run_of(api, run["id"])["status"] == "completed"
    sites = {s["name"]: s for s in sites_of(api, run["id"])}
    store2 = sites["Store 2"]
    assert store2["state"] == "error"
    assert store2["errors"] == [
        {
            "connection": store2["errors"][0]["connection"],
            "connection_name": "Vodacom",
            "message": "The provider's service is unavailable. (HTTP 503)",
            "log": store2["errors"][0]["log"],
        }
    ]
    assert store2["errors"][0]["log"] is not None
    assert {r["product"] for r in store2["results"]} == {chosen[0]}
    # It was retried before giving up.
    calls = [c for c in providers.vodacom.feasibility_calls if c["latitude"] == "-33.9"]
    assert len(calls) == 3
    assert sites_of(api, run["id"], state="error")[0]["name"] == "Store 2"


def test_at_0003_15_i_retry_only_what_failed(api, realm, mtn_and_vodacom, providers):
    providers.vodacom.down.add("-33.9")
    run = start_run(api, picks(mtn_and_vodacom, "Business Fibre"), rows(*SITES)).json()
    before = {r.id for r in FeasibilityResult.objects.in_realm(realm)}
    providers.vodacom.down.clear()
    providers.vodacom.feasibility_calls.clear()
    res = api.post(f"/api/feasibilities/runs/{run['id']}/retry-failed/")
    assert res.status_code == 200
    assert [c["latitude"] for c in providers.vodacom.feasibility_calls] == ["-33.9"]
    assert run_of(api, run["id"])["status"] == "completed"
    assert all(s["state"] == "done" for s in sites_of(api, run["id"]))
    assert before <= {r.id for r in FeasibilityResult.objects.in_realm(realm)}
    assert api.post(f"/api/feasibilities/runs/{run['id']}/retry-failed/").status_code == 400


def test_at_0003_16_i_cancel_a_run(api, realm, mtn_and_vodacom, worker, providers):
    worker.hold()
    run = start_run(api, picks(mtn_and_vodacom, "Business Fibre"), rows(*SITES)).json()
    services.perform_check(realm.id, worker.planned[0])
    res = api.post(f"/api/feasibilities/runs/{run['id']}/cancel/")
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    calls = len(providers.vodacom.feasibility_calls)
    for check_id in worker.planned[1:]:
        assert services.perform_check(realm.id, check_id) == "skipped"
    assert len(providers.vodacom.feasibility_calls) == calls
    states = [s["state"] for s in sites_of(api, run["id"])]
    assert states == ["done", "cancelled", "cancelled"]
    assert api.post(f"/api/feasibilities/runs/{run['id']}/cancel/").status_code == 400


def test_at_0003_17_the_export_keeps_my_spreadsheet(api, mtn_and_vodacom, providers):
    providers.vodacom.down.add("-33.9")
    sites = rows(*SITES)
    sites[0]["row"]["Notes"] = '=HYPERLINK("x")'
    chosen = picks(mtn_and_vodacom, "Business Fibre 100", "Business Fibre")
    run = api.post(
        "/api/feasibilities/runs/",
        {
            "name": "Rollout",
            "products": chosen,
            "rows": sites,
            "columns": ["Site", "Notes", "Lat", "Lon"],
        },
        format="json",
    ).json()
    res = api.get(f"/api/feasibilities/runs/{run['id']}/export/")
    assert res["Content-Type"].startswith("text/csv")
    table = list(csv.reader(io.StringIO(res.content.decode())))
    assert table[0] == [
        "Line",
        "Site",
        "Notes",
        "Lat",
        "Lon",
        "MTN: Business Fibre 100",
        "Vodacom: Business Fibre - Fibre",
        "Vodacom: Business Fibre - Fixed Wireless",
        "Errors",
    ]
    assert table[1] == [
        "2",
        "Depot",
        '\'=HYPERLINK("x")',
        "-26.1",
        "28.0",
        "Available",
        "Available",
        "Coverage only",
        "",
    ]
    assert table[2][5:8] == ["Available", "Error", "Error"]
    assert "Vodacom: The provider's service is unavailable" in table[2][8]


def test_at_0003_18_providers_are_respected(api, realm, mtn_and_vodacom, providers):
    many = [(f"Site {i}", -26 - i / 1000, 28 + i / 1000) for i in range(45)]
    many.append(("Same as site 0", -26, 28))
    run = start_run(
        api, picks(mtn_and_vodacom, "Business LTE", "Business Internet LTE"), rows(*many)
    ).json()
    # MTN takes 20 sites per call: 45 unique places in 3 calls. Vodacom one per call.
    assert [len(c["body"]["inputs"]) for c in providers.mtn.feasibility_calls] == [20, 20, 5]
    assert len(providers.vodacom.feasibility_calls) == 45
    sites = sites_of(api, run["id"])
    assert {r["status"] for r in sites[0]["results"]} == {r["status"] for r in sites[-1]["results"]}
    assert len(sites[-1]["results"]) == len(sites[0]["results"])
    checks = ProviderCheck.objects.in_realm(realm).of_run(run["id"])
    limits = set(services.runtime_for(realm.id, list(checks.values_list("id", flat=True))).values())
    mtn_id = Connection.objects.in_realm(realm).get(name="MTN").id
    voda_id = Connection.objects.in_realm(realm).get(name="Vodacom").id
    assert limits == {(f"connection-{mtn_id}", 2, 30), (f"connection-{voda_id}", 3, 60)}


def test_at_0003_18_hatchet_limits_each_connection():
    from apps.feasibilities.tasks import feasibility_check

    task = feasibility_check._task
    (concurrency,) = task.concurrency
    assert (concurrency.expression, concurrency.max_runs) == (
        "input.limit_key",
        "input.max_concurrency",
    )
    (rate,) = task.rate_limits
    assert rate.key_expr == "input.limit_key"
    assert rate.limit_values_expr == "input.requests_per_minute"


def test_at_0003_19_results_dont_change_after_a_run(api, realm, mtn_and_vodacom, providers):
    chosen = picks(mtn_and_vodacom, "Business Fibre 100")
    first = start_run(api, chosen, rows(*SITES)).json()
    before = sites_of(api, first["id"])
    providers.mtn.not_feasible.update({"-26.1", "-33.9", "-29.85"})
    second = start_run(api, chosen, rows(*SITES), name="Again").json()
    second_sites = sites_of(api, second["id"])
    assert all(s["state"] == "done" and s["results"] == [] for s in second_sites)
    providers.mtn.products = ["Business LTE"]
    from apps.integrations.services import run_operation

    run_operation(
        realm.id, Connection.objects.in_realm(realm).get(name="MTN").id, "sync_products", "manual"
    )
    assert sites_of(api, first["id"]) == before
    assert run_of(api, first["id"])["products"][0]["retired_at"] is not None


def test_at_0003_20_refused_credentials_dont_keep_retrying(api, realm, mtn_and_vodacom, providers):
    providers.mtn.status = 401
    many = [(f"Site {i}", -26 - i / 1000, 28) for i in range(30)]
    run = start_run(
        api, picks(mtn_and_vodacom, "Business LTE", "Business Internet LTE"), rows(*many)
    ).json()
    assert len(providers.mtn.feasibility_calls) == 1
    checks = ProviderCheck.objects.in_realm(realm).of_run(run["id"])
    mtn_checks = checks.filter(connection__name="MTN")
    assert {c.error for c in mtn_checks} == {"The provider refused this connection's credentials."}
    assert Connection.objects.in_realm(realm).get(name="MTN").health == "failing"
    assert checks.filter(connection__name="Vodacom", status="done").count() == 30
    assert run_of(api, run["id"])["status"] == "completed"


def test_at_0003_21_who_can_run_and_see_feasibilities(api, realm, mtn_and_vodacom):
    run = start_run(api, picks(mtn_and_vodacom, "Business LTE"), rows(*SITES)).json()
    path = f"/api/feasibilities/runs/{run['id']}/"
    viewer = client_for(member(realm, "viewer@example.com", "viewer").user, realm)
    assert viewer.get("/api/feasibilities/runs/").status_code == 200
    assert viewer.get(path).status_code == 200
    assert viewer.get(f"{path}sites/").status_code == 200
    assert viewer.get(f"{path}export/").status_code == 200
    attempts = [
        start_run(viewer, picks(mtn_and_vodacom, "Business LTE"), rows(*SITES)),
        viewer.post(f"{path}cancel/"),
        viewer.post(f"{path}retry-failed/"),
        viewer.get("/api/feasibilities/runs/products/"),
    ]
    assert [r.status_code for r in attempts] == [403] * 4

    nobody_role = Role.objects.create(realm=realm, key="outside", name="Outside", permissions=[])
    outsider = member(realm, "outside@example.com", "viewer")
    RealmMembership.objects.in_realm(realm).filter(pk=outsider.pk).update(role=nobody_role)
    client = client_for(outsider.user, realm)
    assert client.get("/api/feasibilities/runs/").status_code == 403
    assert client.get(path).status_code == 403
    assert client.get(f"{path}export/").status_code == 403


def test_at_0003_24_the_demo_connector_runs_without_a_provider(api, realm):
    assert connect(api, "demo", "Demo").status_code == 201
    products = list(ProviderProduct.objects.in_realm(realm).values_list("id", flat=True))
    assert len(products) == 4

    def failing(lat):
        query = demo.SiteQuery("x", "x", Decimal(str(lat)).quantize(Decimal("0.0000001")), 28)
        return demo.fails(query)

    # Demo sends five sites per call; a call fails when its first site is a failing one.
    bad = next(-26 - i / 1000 for i in range(500) if failing(-26 - i / 1000))
    good = [-27 - i / 1000 for i in range(500) if not failing(-27 - i / 1000)][:9]
    many = [("Failing call", bad, 28)] + [(f"Site {i}", lat, 28) for i, lat in enumerate(good)]
    run = start_run(api, products, rows(*many)).json()
    assert run_of(api, run["id"])["status"] == "completed"
    sites = sites_of(api, run["id"])
    assert {s["state"] for s in sites} == {"done", "error"}
    # Predictable: the same sites give the same answers and the same failures again.
    again = start_run(api, products, rows(*many), name="Again").json()

    def summary(site):
        return (site["state"], sorted((r["product"], r["status"]) for r in site["results"]))

    assert [summary(s) for s in sites] == [summary(s) for s in sites_of(api, again["id"])]


def test_only_feasible_answers_are_stored(api, realm, mtn_and_vodacom, providers):
    providers.mtn.not_feasible.add("-33.9")
    start_run(api, picks(mtn_and_vodacom, "Business Fibre 100", "Business Fibre"), rows(*SITES))
    statuses = set(FeasibilityResult.objects.in_realm(realm).values_list("status", flat=True))
    assert statuses == {"available", "coverage_only"}


def test_recorded_calls_never_hold_a_secret(api, realm, mtn_and_vodacom):
    start_run(api, picks(mtn_and_vodacom, "Business LTE", "Business Internet LTE"), rows(*SITES))
    from apps.integration_logs.models import IntegrationLog

    logged = json.dumps(list(IntegrationLog.objects.in_realm(realm).values()), default=str)
    assert MTN_KEY not in logged and "invented-voda-key" not in logged
    assert "[redacted]" in logged


def test_a_retired_product_cant_start_a_run(api, realm, mtn_and_vodacom):
    lte = mtn_and_vodacom["Business LTE"]
    ProviderProduct.objects.in_realm(realm).filter(pk=lte.pk).update(retired_at="2026-01-01T00:00Z")
    res = start_run(api, [lte.id], rows(*SITES))
    assert res.status_code == 400 and "products" in res.json()


def test_deleting_a_company_takes_its_runs_and_connections(api, realm, mtn_and_vodacom):
    from apps.realms.models import Realm

    start_run(api, picks(mtn_and_vodacom, "Business LTE", "Business Internet LTE"), rows(*SITES))
    Realm.objects.filter(pk=realm.pk).delete()
    assert not Connection.objects.in_realm(realm.id).exists()
    assert not FeasibilityResult.objects.in_realm(realm.id).exists()


def _run_of_many(api, realm, count):
    assert connect(api, "demo", "Demo").status_code == 201
    products = list(ProviderProduct.objects.in_realm(realm).values_list("id", flat=True))[:1]
    many = [(f"Site {i:03}", -26 - i / 1000, 28) for i in range(count)]
    return start_run(api, products, rows(*many)).json()["id"]


def test_run_sites_come_twenty_to_a_page(api, realm):
    run_id = _run_of_many(api, realm, 45)
    path = f"/api/feasibilities/runs/{run_id}/sites/"
    first = api.get(path).json()
    assert (first["count"], first["page"], first["page_size"]) == (45, 1, 20)
    assert [s["line_number"] for s in first["results"]] == list(range(2, 22))
    last = api.get(path, {"page": 3}).json()
    assert [s["name"] for s in last["results"]] == [f"Site {i:03}" for i in range(40, 45)]
    # Past the end gives the last page; nonsense gives the first.
    assert api.get(path, {"page": 9}).json()["page"] == 3
    assert api.get(path, {"page": "x"}).json()["page"] == 1
    assert api.get(path, {"page": 0}).json()["page"] == 1
    assert first["previous"] is None and "page=2" in first["next"]


def test_run_sites_page_size_is_one_of_the_offered_sizes(api, realm):
    run_id = _run_of_many(api, realm, 45)
    path = f"/api/feasibilities/runs/{run_id}/sites/"
    for size, shown in [(50, 45), (100, 45), (200, 45), (20, 20)]:
        page = api.get(path, {"page_size": size}).json()
        assert (page["page_size"], len(page["results"])) == (size, shown)
    for odd in [7, 1000, 0, -20, "all"]:
        assert api.get(path, {"page_size": odd}).json()["page_size"] == 20


def test_run_sites_pages_follow_the_search_and_filter(api, realm):
    run_id = _run_of_many(api, realm, 45)
    path = f"/api/feasibilities/runs/{run_id}/sites/"
    found = api.get(path, {"search": "Site 03", "page_size": 50}).json()
    assert found["count"] == 10
    assert [s["name"] for s in found["results"]] == [f"Site {i:03}" for i in range(30, 40)]
    found = api.get(path, {"search": "Site 0", "page": 2}).json()
    assert (found["count"], found["page"], len(found["results"])) == (45, 2, 20)
    states = {"done": 0, "error": 0}
    for state in states:
        page = api.get(path, {"state": state, "page_size": 200}).json()
        states[state] = page["count"]
        assert {s["state"] for s in page["results"]} <= {state}
    assert states["done"] + states["error"] == 45
