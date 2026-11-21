"""Spec 0006: Telejects' price book, API clients, and Rapid's single-site endpoints."""

import io
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.api_clients.models import ApiClient
from apps.integration_logs.models import IntegrationLog
from apps.integrations.models import PlatformAccount
from apps.integrations.services import ensure_default_connections, ensure_platform_accounts
from apps.pricebook import books
from apps.pricebook.models import (
    HEROTEL,
    LINK_AFRICA,
    MTN,
    VODACOM,
    AccessMedium,
    CatalogueProduct,
    ConnectProduct,
    PriceBook,
    PriceBookGrant,
    PriceDefinition,
)
from apps.realms.access_control import ADMIN, PERMISSIONS
from apps.realms.models import RealmMembership
from apps.site_checks import services as site_checks
from apps.site_checks.models import SiteCheck, SiteCheckCall
from conftest import TEST_PASSWORD, client_for, connect, member

pytestmark = pytest.mark.usefixtures("connectors")

RAPID = Path(__file__).resolve().parent / "rapid_responses"
LINK_AFRICA_URL = "https://api.linkafrica.28east.co.za/getfeasibility"
PLACE = {"latitude": -26.1076, "longitude": 28.0567}


def rapid(name: str) -> dict:
    return json.loads((RAPID / name).read_text())


# --- an invented price book, with Rapid's ids ---------------------------------------------------


def make_book():
    book = books.default_book()
    products = {
        23: (VODACOM, "Business Internet LTE", "3", 3),
        24: (VODACOM, "Business Fibre", "10", 10),
        32: (MTN, "Business Fibre 100", "Business Fibre 100", None),
        33: (MTN, "Business LTE", "Business LTE", None),
        40: (HEROTEL, "Herotel Business Fibre", "herotelbusiness", None),
        41: (LINK_AFRICA, "Link Africa Fibre", "link_africa_fibre", None),
    }
    for pk, (provider, name, code, number) in products.items():
        CatalogueProduct.objects.create(
            pk=pk, provider=provider, name=name, product_code=code, product_id=number
        )
    AccessMedium.objects.create(pk=453, provider_access_medium_identifier_id=3, name="Mobile LTE")
    AccessMedium.objects.create(pk=488, provider_access_medium_identifier_id=20, name="Fibre")

    def define(pk, name, *, am=None, product=None, provider=VODACOM, **values):
        values = {
            "duration": 12,
            "monthly_recurring_cost": Decimal("0.00"),
            "none_recurring_cost": Decimal("0.00"),
            "data_allocation": None,
            "data_allocation_notes": "Uncapped",
            "max_bandwidth": 1000,
            "max_upload_bandwidth": 1000,
            "medium": "Fibre",
            **values,
        }
        return PriceDefinition.objects.create(
            pk=pk,
            name=name,
            access_medium_id=am,
            product_id=product,
            provider=provider,
            **values,
        )

    prem = "Sky Connect Prem ( Fibre )"
    voda = [
        define(206, prem, am=488, product=24, monthly_recurring_cost=Decimal("-1"),
               none_recurring_cost=Decimal("-1")),
        define(207, prem, am=488, product=24, duration=24,
               monthly_recurring_cost=Decimal("2086.09"), none_recurring_cost=Decimal("2173.91")),
        define(208, prem, am=488, product=24, max_bandwidth=100, max_upload_bandwidth=100,
               monthly_recurring_cost=Decimal("899.00")),
        define(210, "Sky Connect LTE", am=453, product=23, duration=24, max_bandwidth=50,
               max_upload_bandwidth=10, data_allocation=50, data_allocation_notes="",
               monthly_recurring_cost=Decimal("499.00"), medium="LTE"),
        define(211, "Sky Connect Fibre Lite", am=488, duration=36, max_upload_bandwidth=500,
               monthly_recurring_cost=Decimal("1999.00")),
    ]  # fmt: skip
    mtn = [
        define(220, "MTN Fibre 100", product=32, provider=MTN, duration=24, max_bandwidth=100,
               max_upload_bandwidth=100, monthly_recurring_cost=Decimal("1500.00")),
        define(221, "MTN Fibre 100", product=32, provider=MTN, duration=24, max_bandwidth=200,
               max_upload_bandwidth=200, monthly_recurring_cost=Decimal("2500.00")),
    ]  # fmt: skip
    link = [
        define(230, "Link Fibre 100", product=41, provider=LINK_AFRICA, max_bandwidth=100,
               max_upload_bandwidth=100, monthly_recurring_cost=Decimal("1200.00")),
    ]  # fmt: skip
    for pk, name, description, definitions in [
        (1, "Vodacom Products", "All available Vodacom prices", voda),
        (5, "Connect MTN", "All available MTN prices", mtn),
        (7, "Connect Link Africa", "All Link Africa prices", link),
    ]:
        connect_product = ConnectProduct.objects.create(
            pk=pk, name=name, description=description, book=book
        )
        connect_product.product_definitions.set(definitions)
    books.reset_sequences()
    return book


@pytest.fixture
def book(db):
    return make_book()


def connect_mtn_and_vodacom(client, providers):
    connect(
        client,
        "mtn",
        "MTN",
        api_key="invented-mtn-key-0006",
        requestor_email="ops@northwind.example",
        customer_name="NW",
    )
    connect(client, "vodacom", "Vodacom", auth_key="invented-voda-key", calling_system="NW")
    providers.mtn.feasibility_calls.clear()
    providers.vodacom.feasibility_calls.clear()


@pytest.fixture
def acme(api, realm, book, providers):
    """Northwind Fibre, connected to MTN and Vodacom with its own accounts."""
    connect_mtn_and_vodacom(api, providers)
    return realm


@pytest.fixture
def link_africa(providers):
    """Link Africa's API, invented: feasible everywhere, with two products."""
    calls = []

    def answer(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "feasible": True,
                "bandwidth": "100",
                "products": [{"product": "Link Edge"}, {"product": "Link Business"}],
            },
        )

    providers.router.get(LINK_AFRICA_URL).mock(side_effect=answer)
    return calls


# --- API clients ---------------------------------------------------------------------------------


def make_client(admin_api, permissions, name="Acme integration"):
    res = admin_api.post(
        "/api/api-clients/", {"name": name, "permissions": permissions}, format="json"
    )
    assert res.status_code == 201, res.content
    return res.json()


def token_of(created) -> str:
    res = APIClient().post(
        "/api/oauth/token/",
        urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": created["client_id"],
                "client_secret": created["client_secret"],
            }
        ),
        content_type="application/x-www-form-urlencoded",
    )
    assert res.status_code == 200, res.content
    return res.json()["access_token"]


def bearer(token: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def machine(api, acme):
    """Acme's integration: an API client allowed to check and quote, with its token."""
    created = make_client(api, ["feasibilities.run", "feasibilities.quote"])
    return bearer(token_of(created))


def ids_replaced(body: dict) -> dict:
    """The response with one-site result ids replaced, after checking they are unique ints."""
    ids = [row["id"] for row in body["data"]]
    assert all(isinstance(i, int) for i in ids)
    assert len(set(ids)) == len(ids)
    return {**body, "data": [{**row, "id": "<result>"} for row in body["data"]]}


# --- the price book in Django admin -------------------------------------------------------------


def rapid_dump() -> str:
    return json.dumps(
        [
            {"model": "connect.product", "pk": 23,
             "fields": {"product_id": 3, "name": "Business Internet LTE", "provider": 0}},
            {"model": "connect.product", "pk": 32,
             "fields": {"product_id": None, "name": "Business Fibre 100", "provider": 1}},
            {"model": "connect.accessmedium", "pk": 453,
             "fields": {"provider_access_medium_identifier_id": 3, "name": "Mobile LTE"}},
            {"model": "connect.connectproductdefinition", "pk": 210,
             "fields": {"name": "Sky Connect LTE", "access_medium": 453, "product": 23,
                        "provider": 0, "sublayer": 9, "duration": 24,
                        "monthly_recurring_cost": "499.00", "none_recurring_cost": "-1.00",
                        "data_allocation": 50, "data_allocation_notes": "",
                        "max_bandwidth": 50, "max_upload_bandwidth": 10, "medium": "LTE"}},
            {"model": "connect.connectproductdefinition", "pk": 220,
             "fields": {"name": "MTN Fibre 100", "access_medium": None, "product": 32,
                        "provider": 1, "sublayer": None, "duration": 24,
                        "monthly_recurring_cost": "1500.00", "none_recurring_cost": "0.00",
                        "data_allocation": None, "data_allocation_notes": "Uncapped",
                        "max_bandwidth": 100, "max_upload_bandwidth": 100, "medium": "Fibre"}},
            {"model": "connect.connectproduct", "pk": 6,
             "fields": {"name": "Connect Vodacom", "description": "All Vodacom prices",
                        "product_definitions": [210]}},
            {"model": "connect.connectproduct", "pk": 5,
             "fields": {"name": "Connect MTN", "description": None,
                        "product_definitions": [220]}},
            {"model": "connect.realm", "pk": 1, "fields": {"name": "ignored"}},
        ]
    )  # fmt: skip


def book_state():
    return (
        sorted(CatalogueProduct.objects.values_list("id", "name", "provider", "product_code")),
        sorted(AccessMedium.objects.values_list("id", "name")),
        sorted(
            PriceDefinition.objects.values_list(
                "id", "name", "monthly_recurring_cost", "none_recurring_cost", "max_bandwidth"
            )
        ),
        sorted(
            (c.id, c.name, tuple(c.product_definitions.values_list("id", flat=True)))
            for c in ConnectProduct.objects.all()
        ),
    )


def test_at_0006_01_staff_import_rapids_price_book_with_its_ids(db, tmp_path):
    dump = tmp_path / "pricebook.json"
    dump.write_text(rapid_dump())
    from django.core.management import call_command

    call_command("import_rapid_pricebook", str(dump), stdout=io.StringIO())
    first = book_state()
    assert first[0] == [
        (23, "Business Internet LTE", VODACOM, "3"),
        (32, "Business Fibre 100", MTN, "Business Fibre 100"),
    ]
    assert first[1] == [(453, "Mobile LTE")]
    assert first[2] == [
        (210, "Sky Connect LTE", Decimal("499.00"), Decimal("-1.00"), 50),
        (220, "MTN Fibre 100", Decimal("1500.00"), Decimal("0.00"), 100),
    ]
    assert first[3] == [(5, "Connect MTN", (220,)), (6, "Connect Vodacom", (210,))]
    assert ConnectProduct.objects.get(pk=6).book.name == "Telejects"

    call_command("import_rapid_pricebook", str(dump), stdout=io.StringIO())
    assert book_state() == first
    # New rows made afterwards don't collide with Rapid's ids.
    assert AccessMedium.objects.create(provider_access_medium_identifier_id=9, name="New").pk > 453


@pytest.fixture
def staff(db):
    return get_user_model().objects.create_superuser(
        email="staff@telejects.example", password=TEST_PASSWORD
    )


def staff_client(staff):
    from django.test import Client

    client = Client()
    client.force_login(staff)
    return client


def test_at_0006_02_staff_import_price_definitions_from_rapids_csv(book, staff):
    out = io.StringIO()
    import csv

    writer = csv.writer(out)
    writer.writerow(books.CSV_COLUMNS)
    writer.writerow(
        ["Vodacom", "453", "Mobile LTE", "Business Internet LTE", "3", "Sky Connect LTE Max",
         "MRC on Request only", "NRC on Request only", "12", "", "Uncapped", "Unrestricted", "",
         "LTE"]
    )  # fmt: skip
    writer.writerow(
        ["MTN", "", "", "Business Fibre 100", "", "Connect MTN Business", "R1,234.50", "R0",
         "24", "", "Uncapped", "100", "100", "Fibre"]
    )  # fmt: skip
    writer.writerow(["Nowhere Telecom", "", "", "", "", "Bad", "1", "1", "12"])
    upload = io.BytesIO(out.getvalue().encode())
    upload.name = "prices.csv"
    res = staff_client(staff).post(
        "/admin/pricebook/pricedefinition/import/", {"csv_file": upload}, follow=True
    )
    assert res.status_code == 200
    shown = [str(m) for m in res.context["messages"]]
    assert shown == ["3 rows processed. Updated 1 and created 1. 1 row failures."]
    lte = PriceDefinition.objects.get(name="Sky Connect LTE Max")
    assert lte.monthly_recurring_cost == lte.none_recurring_cost == Decimal("-1.00")
    assert (lte.access_medium_id, lte.max_bandwidth, lte.max_upload_bandwidth) == (453, 100, 100)
    assert list(
        ConnectProduct.objects.get(name="Sky Connect LTE Max").product_definitions.all()
    ) == [lte]
    # The MTN row matches definition 220: it is updated, renamed, and moves connect product.
    mtn = PriceDefinition.objects.get(name="Connect MTN Business")
    assert (mtn.pk, mtn.monthly_recurring_cost) == (220, Decimal("1234.50"))
    assert list(mtn.connect_products.values_list("name", flat=True)) == ["Connect MTN Business"]
    assert list(
        ConnectProduct.objects.get(pk=5).product_definitions.values_list("pk", flat=True)
    ) == [221]


def test_at_0006_03_staff_download_the_price_book_as_csv_and_pdf(book, staff):
    client = staff_client(staff)
    res = client.get("/admin/pricebook/pricedefinition/export-csv/")
    assert res.status_code == 200 and res["Content-Type"] == "text/csv"
    lines = res.content.decode().splitlines()
    assert lines[0].startswith("Provider,Product Name,Access Medium")
    assert lines[1].split(",")[:3] == ["Vodacom", "Sky Connect Prem ( Fibre )", "Fibre"]
    assert any(line.endswith(",POA,POA") for line in lines)
    providers = [line.split(",")[0] for line in lines[1:]]
    assert providers == sorted(providers, key=["Vodacom", "MTN", "LINK_AFRICA"].index)
    assert len(lines) == 1 + PriceDefinition.objects.count()

    pdf = client.get("/admin/pricebook/pricedefinition/export-pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    template = client.get("/admin/pricebook/pricedefinition/template/")
    assert template.content.decode().count("\n") == 1 + AccessMedium.objects.count()


def test_the_price_book_files_are_staff_only(book, realm, user):
    from django.test import Client

    client = Client()
    client.force_login(user)  # an Admin of a company, not platform staff
    for path in ("export-csv/", "export-pdf/", "template/", "import/"):
        res = client.get(f"/admin/pricebook/pricedefinition/{path}")
        assert res.status_code == 302 and "/admin/login/" in res["Location"]


# --- API clients ---------------------------------------------------------------------------------


def test_at_0006_04_an_admin_creates_an_api_client_and_sees_its_secret_once(api, realm):
    created = make_client(api, ["feasibilities.run", "feasibilities.quote"])
    assert created["client_secret"] and created["client_id"]
    assert created["permissions"] == ["feasibilities.run", "feasibilities.quote"]
    listed = api.get("/api/api-clients/").json()
    assert [c["client_id"] for c in listed] == [created["client_id"]]
    assert "client_secret" not in listed[0]
    detail = api.get(f"/api/api-clients/{created['id']}/").json()
    assert "client_secret" not in detail
    # Stored hashed: the secret itself is nowhere in the database.
    application = ApiClient.objects.in_realm(realm).get().application
    assert created["client_secret"] not in application.client_secret


def test_a_client_is_offered_only_what_clients_can_use_and_i_may_do(api, realm):
    offered = api.get("/api/api-clients/permissions/").json()
    assert offered == [
        {"code": "feasibilities.run", "label": PERMISSIONS["feasibilities.run"]},
        {"code": "feasibilities.quote", "label": PERMISSIONS["feasibilities.quote"]},
    ]
    res = api.post(
        "/api/api-clients/", {"name": "Too much", "permissions": ["users.manage"]}, format="json"
    )
    assert res.status_code == 400
    assert ApiClient.objects.in_realm(realm).count() == 0


def test_a_deleted_companys_clients_take_their_applications_with_them(api, realm):
    from oauth2_provider.models import Application

    make_client(api, ["feasibilities.run"])
    assert Application.objects.count() == 1
    realm.delete()
    assert Application.objects.count() == 0


def test_an_admin_cant_give_a_client_more_than_they_have(realm, api):
    pm = member(realm, "pm@northwind.example", "project_manager")
    res = client_for(pm.user, realm).post(
        "/api/api-clients/", {"name": "PM's", "permissions": ["feasibilities.run"]}, format="json"
    )
    assert res.status_code == 403  # making clients needs api_clients.manage
    res = api.post("/api/api-clients/", {"name": "x", "permissions": []}, format="json")
    assert res.status_code == 400


def test_at_0006_05_a_client_gets_a_token_and_works_in_its_company_without_x_realm(machine, acme):
    res = machine.get("/api/product/")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == CatalogueProduct.objects.count()
    assert body["results"][0] == {
        "id": 24,
        "provider_verbose": {"id": 0, "name": "Vodacom"},
        "name": "Business Fibre",
        "provider": 0,
    }
    assert machine.get("/api/product/?provider=0").json()["count"] == 2
    assert machine.get("/api/product/?search_string=lte").json()["count"] == 2
    assert machine.get("/api/product/24/").json()["name"] == "Business Fibre"


def test_a_client_token_works_on_rapids_endpoints_only(machine):
    assert machine.get("/api/auth/me/").status_code == 401
    assert machine.get("/api/users/").status_code == 401
    assert machine.get("/api/feasibilities/runs/").status_code == 401


def test_at_0006_06_a_client_cant_do_more_than_its_scopes(api, acme):
    only_run = bearer(token_of(make_client(api, ["feasibilities.run"], name="Checker")))
    res = only_run.post("/api/single-site-feasibility-quote/", PLACE, format="json")
    assert res.status_code == 403
    assert only_run.get("/api/connect-product/").status_code == 403
    assert only_run.get("/api/product/").status_code == 200


def test_a_client_loses_what_its_maker_loses(api, realm, acme):
    pm = member(realm, "pm@northwind.example", ADMIN)
    created = make_client(client_for(pm.user, realm), ["feasibilities.run"], name="PM's")
    machine = bearer(token_of(created))
    assert machine.get("/api/product/").status_code == 200
    membership = RealmMembership.objects.in_realm(realm).get(user=pm.user)
    membership.role = realm_role(realm, "viewer")
    membership.save()
    assert machine.get("/api/product/").status_code == 403
    membership.status = RealmMembership.Status.REMOVED
    membership.save()
    assert machine.get("/api/product/").status_code == 401


def realm_role(realm, key):
    from apps.realms.models import Role

    return Role.objects.in_realm(realm).by_key(key)


def test_at_0006_07_a_revoked_clients_token_stops_working(api, acme):
    created = make_client(api, ["feasibilities.run"])
    machine = bearer(token_of(created))
    assert machine.get("/api/product/").status_code == 200
    res = api.delete(f"/api/api-clients/{created['id']}/")
    assert res.status_code == 200 and res.json()["active"] is False
    assert machine.get("/api/product/").status_code == 401
    again = APIClient().post(
        "/api/oauth/token/",
        urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": created["client_id"],
                "client_secret": created["client_secret"],
            }
        ),
        content_type="application/x-www-form-urlencoded",
    )
    assert again.status_code == 401


# --- Rapid's endpoints ---------------------------------------------------------------------


def test_at_0006_08_connect_products_list_matches_rapid(machine):
    res = machine.get("/api/connect-product/")
    assert res.status_code == 200
    assert res.json() == rapid("connect_products.json")
    paged = machine.get("/api/connect-product/?page_size=2").json()
    assert paged["count"] == 3 and len(paged["results"]) == 2
    assert paged["next"].endswith("/api/connect-product/?page=2&page_size=2")
    assert machine.get("/api/connect-product/?search_string=mtn").json()["count"] == 1
    assert (
        machine.get("/api/connect-product/1/").json()
        == rapid("connect_products.json")["results"][2]
    )


def test_connect_products_are_paged_by_twenty(machine, book):
    for i in range(25):
        ConnectProduct.objects.create(name=f"Extra {i:02}", book=book)
    body = machine.get("/api/connect-product/").json()
    assert body["count"] == 28 and len(body["results"]) == 20


def test_at_0006_09_a_single_site_check_matches_rapids_response(machine, providers):
    res = machine.post("/api/single-site-feasibility/", PLACE, format="json")
    assert res.status_code == 200, res.content
    assert ids_replaced(res.json()) == rapid("single_site.json")
    # Each provider was asked once, about the place.
    assert len(providers.vodacom.feasibility_calls) == 1
    assert len(providers.mtn.feasibility_calls) == 1
    assert providers.vodacom.feasibility_calls[0]["latitude"] == "-26.1076"


def test_a_single_site_check_asks_only_for_the_products_named(machine, providers):
    body = machine.post(
        "/api/single-site-feasibility/", {**PLACE, "products": [32]}, format="json"
    ).json()
    assert [row["access_medium"]["product"]["id"] for row in body["data"]] == [32]
    assert providers.vodacom.feasibility_calls == []
    assert providers.mtn.feasibility_calls[0]["body"]["product_names"] == ["Business Fibre 100"]


def test_at_0006_10_a_quote_matches_rapids_response(machine, link_africa, api):
    connect(api, "link_africa", "Link Africa", api_key="invented-la", bandwidth_mbps="100",
            term_months="24")  # fmt: skip
    res = machine.post("/api/single-site-feasibility-quote/", PLACE, format="json")
    assert res.status_code == 200, res.content
    assert res.json() == rapid("quote.json")


def test_at_0006_11_only_definitions_at_an_offered_bandwidth_are_priced(machine):
    body = machine.post(
        "/api/single-site-feasibility-quote/", {**PLACE, "connect_products": [1]}, format="json"
    ).json()
    priced = {o["id"]: o["max_bandwidth"] for p in body["data"][0]["products"]
              for o in p["price_options"]}  # fmt: skip
    # Fibre is offered at 100-1000 and 1000 (tops: 1000), LTE at 0-50.
    assert priced == {206: 1000, 207: 1000, 211: 1000, 210: 50}
    assert 208 not in priced  # 100 Mbps isn't the top of a range offered there


def test_at_0006_12_a_provider_that_times_out_is_listed_and_the_rest_still_answer(
    machine, monkeypatch
):
    clock = {"now": 0.0}
    monkeypatch.setattr(site_checks, "_now", lambda: clock["now"])
    monkeypatch.setattr(site_checks, "_sleep", lambda s: clock.__setitem__("now", clock["now"] + s))
    real = site_checks.perform_call

    def mtn_never_answers(realm_id, call_ids):
        for call_id in call_ids:
            call = SiteCheckCall.objects.in_realm_id(realm_id).get(pk=call_id)
            if call.connector_key != "mtn":
                real(realm_id, call_id)

    monkeypatch.setattr(site_checks, "_enqueue_calls", mtn_never_answers)
    res = machine.post(
        "/api/single-site-feasibility-quote/",
        {**PLACE, "timeout": 5, "connect_products": [1, 5]},
        format="json",
    )
    body = res.json()
    assert res.status_code == 200
    assert 5 <= clock["now"] < 5.5  # waited out the timeout, not the provider's own
    assert [p["connect_product_id"] for p in body["data"]] == [1]
    assert body["exceptions"] == [
        {"exception": "Timeout", "message": "mtn didn't answer within 5 seconds."}
    ]


def test_a_provider_that_fails_is_listed_and_the_rest_still_answer(machine, providers):
    providers.mtn.status = 503
    body = machine.post(
        "/api/single-site-feasibility-quote/", {**PLACE, "connect_products": [1, 5]}, format="json"
    ).json()
    assert [p["connect_product_id"] for p in body["data"]] == [1]
    assert len(body["exceptions"]) == 1
    assert body["exceptions"][0]["exception"] == "ProviderDown"
    assert body["exceptions"][0]["message"].startswith("mtn: ")


def test_at_0006_13_a_provider_the_company_isnt_connected_to_is_listed_not_checked(machine):
    res = machine.post(
        "/api/single-site-feasibility/", {**PLACE, "products": [40, 32]}, format="json"
    )
    body = res.json()
    assert body["exceptions"] == [
        {"exception": "NotConnected", "message": "Not connected to herotel."}
    ]
    assert [row["access_medium"]["product"]["id"] for row in body["data"]] == [32]


@pytest.mark.parametrize(
    ("body", "errors"),
    [
        ({**PLACE, "connect_products": [999]},
         {"connect_products": ["One or more connect_products are invalid."]}),
        ({"longitude": 28.0}, {"latitude": ["This field is required."]}),
        ({**PLACE, "timeout": 60}, {"timeout": ["Ensure this value is less than or equal to 50."]}),
        ({**PLACE, "timeout": 2},
         {"timeout": ["Ensure this value is greater than or equal to 5."]}),
    ],
)  # fmt: skip
def test_at_0006_14_bad_requests_get_rapids_errors(machine, body, errors):
    res = machine.post("/api/single-site-feasibility-quote/", body, format="json")
    assert res.status_code == 400
    assert res.json() == errors


def test_bad_single_site_requests_get_rapids_errors(machine):
    res = machine.post("/api/single-site-feasibility/", {**PLACE, "products": [999]}, format="json")
    assert (res.status_code, res.json()) == (
        400,
        {"products": ["One or more products are invalid."]},
    )


def test_a_failure_inside_the_check_gets_rapids_error(machine, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(site_checks, "start_check", broken)
    res = machine.post("/api/single-site-feasibility-quote/", PLACE, format="json")
    assert res.status_code == 400
    assert res.json() == {"error": "Failed to conduct feasibility: database went away"}


def test_at_0006_15_a_company_without_a_grant_sees_no_price_book(machine, acme, book):
    book.available_to_all = False
    book.save()
    assert machine.get("/api/connect-product/").status_code == 403
    assert (
        machine.post("/api/single-site-feasibility-quote/", PLACE, format="json").status_code == 403
    )
    PriceBookGrant.objects.create(realm=acme, book=book)
    assert machine.get("/api/connect-product/").status_code == 200


def test_at_0006_16_one_site_checks_use_the_companys_credentials_and_are_logged(
    api, realm, book, providers, settings
):
    settings.INTEGRATIONS_PLATFORM_ACCOUNTS = {
        "vodacom": {
            "secrets": {"auth_key": "telejects-voda-key-invented"},
            "settings": {"calling_system": "Telejects"},
        }
    }
    ensure_platform_accounts()
    ensure_default_connections(realm)
    connect(api, "mtn", "MTN", api_key="northwind-own-mtn-key", requestor_email="o@nw.example",
            customer_name="NW")  # fmt: skip
    machine = bearer(token_of(make_client(api, ["feasibilities.run", "feasibilities.quote"])))
    providers.vodacom.feasibility_calls.clear()
    providers.mtn.feasibility_calls.clear()
    res = machine.post("/api/single-site-feasibility/", PLACE, format="json")
    assert res.status_code == 200 and res.json()["exceptions"] == []
    assert providers.vodacom.feasibility_calls[0]["callingSystem"] == "Telejects"
    assert providers.mtn.feasibility_calls[0]["headers"]["x-api-key"] == "northwind-own-mtn-key"
    check = SiteCheck.objects.in_realm(realm).get()
    assert check.api_client_id == ApiClient.objects.in_realm(realm).get().id
    logs = IntegrationLog.objects.in_realm(realm).filter(site_check_id=check.id)
    assert sorted(logs.values_list("connector_key", "credentials")) == [
        ("mtn", "own"),
        ("vodacom", "platform"),
    ]
    text = json.dumps(list(logs.values("request_headers", "request_body", "url")))
    assert "telejects-voda-key-invented" not in text and "northwind-own-mtn-key" not in text
    assert "Telejects" not in text  # a platform account's settings are hidden too
    assert PlatformAccount.objects.get(connector_key="vodacom")


def test_a_signed_in_member_may_use_rapids_endpoints_too(api, acme):
    res = api.post("/api/single-site-feasibility-quote/", PLACE, format="json")
    assert res.status_code == 200
    assert SiteCheck.objects.in_realm(acme).get().requested_by is not None


def test_at_0006_18_link_africa_and_herotel_arent_priced(machine, link_africa, api):
    connect(api, "link_africa", "Link Africa", api_key="invented-la", bandwidth_mbps="100",
            term_months="24")  # fmt: skip
    link_africa.clear()
    body = machine.post(
        "/api/single-site-feasibility-quote/", {**PLACE, "connect_products": [7]}, format="json"
    ).json()
    assert len(link_africa) == 1  # it was checked, and is feasible
    assert body["data"] == [] and body["exceptions"] == []
    single = machine.post(
        "/api/single-site-feasibility/", {**PLACE, "products": [41]}, format="json"
    ).json()
    assert single["data"][0]["access_medium"] == {
        "product": {"id": 41, "name": "Link Africa Fibre", "provider_name": "LINK_AFRICA"}
    }


def test_offered_books_follow_the_grant(acme, book):
    assert list(PriceBook.objects.offered_to(acme.id)) == [book]
    book.available_to_all = False
    book.save()
    assert list(PriceBook.objects.offered_to(acme.id)) == []


# --- the price book in the portal (Rapid's price book admin page) --------------------------------


@pytest.fixture
def staff_api(realm, book):
    """Telejects staff, working in Northwind like any member."""
    staff = member(realm, "keeper@telejects.example", "viewer").user
    staff.is_staff = True
    staff.save()
    return client_for(staff, realm)


NEW_PRICE = {
    "name": "Sky Connect Fibre Max",
    "access_medium": 488,
    "product": 24,
    "duration": 24,
    "monthly_recurring_cost": "-1",
    "none_recurring_cost": "0",
    "data_allocation": None,
    "data_allocation_notes": "Uncapped",
    "max_bandwidth": 500,
    "max_upload_bandwidth": 250,
    "medium": "Fibre",
    "sublayer": 10,
    "connect_products": [1, 5],
}


def test_at_0006_19_staff_keep_the_price_book_in_the_portal(staff_api):
    res = staff_api.post("/api/price-book/definitions/", NEW_PRICE, format="json")
    assert res.status_code == 201, res.json()
    made = res.json()
    assert made == {
        "id": made["id"],
        "access_medium": {
            "id": 488,
            "name": "Fibre",
            "provider_access_medium_identifier_id": 20,
            "product": None,
        },
        "product": {"id": 24, "name": "Business Fibre", "provider_name": "Vodacom"},
        "connect_products": [
            {"id": 1, "name": "Vodacom Products"},
            {"id": 5, "name": "Connect MTN"},
        ],
        "name": "Sky Connect Fibre Max",
        "provider": VODACOM,
        "sublayer": 10,
        "duration": 24,
        "monthly_recurring_cost": "-1.00",
        "none_recurring_cost": "0.00",
        "data_allocation": None,
        "data_allocation_notes": "Uncapped",
        "max_bandwidth": 500,
        "max_upload_bandwidth": 250,
        "medium": "Fibre",
    }
    path = f"/api/price-book/definitions/{made['id']}/"
    changed = {**NEW_PRICE, "monthly_recurring_cost": "3199.00", "connect_products": [1]}
    res = staff_api.put(path, changed, format="json")
    assert res.status_code == 200
    assert res.json()["monthly_recurring_cost"] == "3199.00"
    assert [c["id"] for c in res.json()["connect_products"]] == [1]
    assert staff_api.delete(path).status_code == 204
    assert not PriceDefinition.objects.filter(pk=made["id"]).exists()

    # Connect products: made, renamed and removed; their prices stay.
    res = staff_api.post(
        "/api/price-book/connect-products/",
        {"name": "Sky Connect Business", "description": "Business lines"},
        format="json",
    )
    assert res.status_code == 201
    created = res.json()
    assert created == {
        "id": created["id"],
        "name": "Sky Connect Business",
        "description": "Business lines",
        "definition_count": 0,
    }
    assert ConnectProduct.objects.get(pk=created["id"]).book.name == "Telejects"
    path = f"/api/price-book/connect-products/{created['id']}/"
    res = staff_api.put(path, {"name": "Sky Connect Biz"}, format="json")
    assert res.json()["name"] == "Sky Connect Biz"
    listed = staff_api.get("/api/price-book/connect-products/").json()
    assert [(c["id"], c["definition_count"]) for c in listed if c["id"] in (1, 5)] == [
        (5, 2),
        (1, 5),
    ]
    assert staff_api.delete("/api/price-book/connect-products/5/").status_code == 204
    assert PriceDefinition.objects.filter(pk__in=[220, 221]).count() == 2


def test_at_0006_20_staff_search_filter_and_page_the_price_book(staff_api):
    def ids(query=""):
        body = staff_api.get(f"/api/price-book/definitions/?{query}").json()
        return [row["id"] for row in body["results"]]

    assert ids() == [230, 221, 220, 211, 210, 208, 207, 206]  # newest first, as in Rapid
    assert ids("search_string=lte") == [210]  # the definition's name
    assert ids("search_string=business fibre 100") == [221, 220]  # its product's name
    assert ids("provider=1") == [221, 220]
    assert ids("medium=LTE") == [210]
    assert ids("product=24") == [208, 207, 206]
    assert ids("provider=x") == []
    body = staff_api.get("/api/price-book/definitions/?page_size=3&page=2").json()
    assert body["count"] == 8 and [r["id"] for r in body["results"]] == [211, 210, 208]
    assert staff_api.get("/api/price-book/definitions/").json()["next"] is None  # 100 a page

    options = staff_api.get("/api/price-book/options/").json()
    assert options["can_edit"] is True
    assert options["providers"][:2] == [
        {"value": 0, "label": "Vodacom"},
        {"value": 1, "label": "MTN"},
    ]
    assert options["mediums"][:5] == ["Fibre", "Wireless", "LTE", "5G", "Wireless and Fibre"]
    assert {"value": 10, "label": "Vumatel"} in options["sublayers"]
    assert [m["id"] for m in options["access_media"]] == [488, 453]


@pytest.mark.parametrize(
    "change, errors",
    [
        ({"access_medium": None, "product": None}, {
            "non_field_errors": ["Either product or access_medium must be set."]}),
        ({"product": 32, "provider": 0}, {
            "provider": ["Provider must match the product's provider."]}),
        ({"product": None, "provider": 1}, {
            "provider": ["Only Vodacom can use access_medium without a product."]}),
        ({"product": 32, "provider": None}, {
            "access_medium": ["Only Vodacom prices an access medium."]}),
        ({"monthly_recurring_cost": "-5"}, {
            "monthly_recurring_cost": ["A cost is zero or more, or -1 for price on request."]}),
        ({"duration": 61}, {"duration": ["Ensure this value is less than or equal to 60."]}),
        ({"name": "Sky Connect Prem ( Fibre )", "duration": 12, "max_bandwidth": 1000,
          "max_upload_bandwidth": 1000}, {
            "non_field_errors": ["The price book already has this price, with this term."]}),
    ],
)  # fmt: skip
def test_at_0006_21_a_price_follows_rapids_rules(staff_api, change, errors):
    res = staff_api.post("/api/price-book/definitions/", {**NEW_PRICE, **change}, format="json")
    assert res.status_code == 400
    assert res.json() == errors


def test_an_mtn_price_takes_its_provider_from_its_product(staff_api):
    body = {**NEW_PRICE, "access_medium": None, "product": 32, "provider": None}
    res = staff_api.post("/api/price-book/definitions/", body, format="json")
    assert res.status_code == 201 and res.json()["provider"] == MTN


def test_at_0006_22_a_member_who_quotes_reads_what_their_company_is_offered(api, realm, book):
    """Northwind's Admin may quote: they see the offered book read-only, and nothing of a book
    Northwind isn't offered, even on a price both books share."""
    other = PriceBook.objects.create(name="Reseller", available_to_all=False)
    hidden = ConnectProduct.objects.create(name="Reseller Fibre", book=other)
    secret = PriceDefinition.objects.create(
        name="Reseller only", product_id=32, provider=MTN, monthly_recurring_cost=Decimal("1"),
        none_recurring_cost=Decimal("0"), max_bandwidth=10, max_upload_bandwidth=10,
    )  # fmt: skip
    hidden.product_definitions.set([secret, PriceDefinition.objects.get(pk=206)])

    body = api.get("/api/price-book/definitions/").json()
    assert [r["id"] for r in body["results"]] == [230, 221, 220, 211, 210, 208, 207, 206]
    shared = body["results"][-1]
    assert shared["connect_products"] == [{"id": 1, "name": "Vodacom Products"}]
    assert "Reseller" not in api.get("/api/price-book/definitions/").content.decode()
    assert api.get(f"/api/price-book/definitions/{secret.id}/").status_code == 404
    listed = api.get("/api/price-book/connect-products/").json()
    assert [c["name"] for c in listed] == ["Connect Link Africa", "Connect MTN", "Vodacom Products"]
    assert api.get(f"/api/price-book/connect-products/{hidden.id}/").status_code == 404
    assert api.get("/api/price-book/options/").json()["can_edit"] is False

    csv_file = api.get("/api/price-book/export/csv/")
    assert csv_file.status_code == 200 and csv_file["Content-Type"] == "text/csv"
    lines = csv_file.content.decode().splitlines()
    assert len(lines) == 1 + 8 and "Reseller" not in csv_file.content.decode()
    pdf = api.get("/api/price-book/export/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # Read-only: every change is refused, and nothing changed.
    before = book_state()
    assert api.post("/api/price-book/definitions/", NEW_PRICE, format="json").status_code == 403
    assert api.put("/api/price-book/definitions/206/", NEW_PRICE, format="json").status_code == 403
    assert api.delete("/api/price-book/definitions/206/").status_code == 403
    assert (
        api.post("/api/price-book/connect-products/", {"name": "Mine"}, format="json").status_code
        == 403
    )
    assert (
        api.put("/api/price-book/connect-products/1/", {"name": "x"}, format="json").status_code
        == 403
    )
    assert api.delete("/api/price-book/connect-products/1/").status_code == 403
    assert book_state() == before


def test_staff_see_and_export_every_book(staff_api):
    other = PriceBook.objects.create(name="Reseller", available_to_all=False)
    ConnectProduct.objects.create(name="Reseller Fibre", book=other)
    names = [c["name"] for c in staff_api.get("/api/price-book/connect-products/").json()]
    assert "Reseller Fibre" in names
    lines = staff_api.get("/api/price-book/export/csv/").content.decode().splitlines()
    assert len(lines) == 1 + PriceDefinition.objects.count()


def test_me_says_whether_i_am_telejects_staff(api, staff_api):
    assert api.get("/api/auth/me/").json()["is_staff"] is False
    assert staff_api.get("/api/auth/me/").json()["is_staff"] is True
