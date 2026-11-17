"""Every provider Telejects has an account for in .env, active for every company from the start,
with each company free to use its own account instead (0004, decision 8)."""

import httpx
import pytest
import respx

from apps.integrations import services
from apps.integrations.canonical import ProductRef, Status
from apps.integrations.engine import build_connector
from apps.integrations.models import Connection, PlatformAccount, ProviderProduct
from apps.integrations.test_engine import site, spec_of
from apps.realms.services import create_realm
from conftest import client_for, member

pytestmark = pytest.mark.usefixtures("connectors")

KEY = "invented-telejects-key"


@pytest.fixture
def env_accounts(settings, providers):
    """.env with Telejects keys for MTN and Vodacom, none for Herotel, and Demo on."""
    settings.INTEGRATIONS_PLATFORM_ACCOUNTS = {
        "mtn": {
            "secrets": {"api_key": KEY},
            "settings": {"requestor_email": "ops@telejects.example", "customer_name": "Telejects"},
        },
        "vodacom": {"secrets": {"auth_key": KEY}, "settings": {"calling_system": "Telejects"}},
        "herotel": {"secrets": {"api_key": ""}, "settings": {}},
        "demo": {"secrets": {}, "settings": {}},
    }
    return settings


def test_every_configured_provider_is_active_for_a_company_from_the_start(env_accounts, realm, api):
    ready = {a.connector_key for a in services.ensure_platform_accounts()}
    assert ready == {"mtn", "vodacom", "demo"}
    services.ensure_default_connections(realm)
    listed = api.get("/api/integrations/connections/").json()
    assert {(c["connector_key"], c["credentials"], c["health"]) for c in listed} == {
        ("mtn", "platform", "ok"),
        ("vodacom", "platform", "ok"),
        ("demo", "platform", "ok"),
    }
    assert ProviderProduct.objects.in_realm(realm).filter(connection__connector_key="mtn").exists()
    connectors = {c["key"]: c["included"] for c in api.get("/api/integrations/connectors/").json()}
    assert connectors == {
        "mtn": True,
        "vodacom": True,
        "demo": True,
        "herotel": False,
        "link_africa": False,
    }
    # Running it again adds nothing.
    assert services.ensure_default_connections(realm) == []


def test_a_new_company_gets_them_and_existing_ones_too(
    env_accounts, realm, django_capture_on_commit_callbacks
):
    services.ensure_platform_accounts()
    with django_capture_on_commit_callbacks(execute=True):
        blue = create_realm("Blue Mast Telecom")
    assert {c.connector_key for c in Connection.objects.in_realm(blue)} == {
        "mtn",
        "vodacom",
        "demo",
    }
    # A company that existed before the keys were set gets them from ensure_everywhere.
    assert not Connection.objects.in_realm(realm).exists()
    services.ensure_everywhere()
    assert {c.connector_key for c in Connection.objects.in_realm(realm)} == {
        "mtn",
        "vodacom",
        "demo",
    }


def test_a_company_overrides_a_provider_with_its_own_account_and_back(
    env_accounts, realm, api, providers
):
    services.ensure_platform_accounts()
    services.ensure_default_connections(realm)
    mtn = Connection.objects.in_realm(realm).get(connector_key="mtn")
    path = f"/api/integrations/connections/{mtn.id}/"
    fields = {
        "api_key": "invented-own-key",
        "requestor_email": "ops@nw.example",
        "customer_name": "NW",
    }
    assert (
        api.patch(path, {"credentials": "own", "fields": fields}, format="json").json()[
            "credentials"
        ]
        == "own"
    )
    assert (
        api.patch(path, {"credentials": "platform"}, format="json").json()["credentials"]
        == "platform"
    )


def test_a_company_with_its_own_account_keeps_it(env_accounts, realm, api, providers):
    from conftest import connect

    connect(
        api,
        "mtn",
        "Our MTN",
        api_key="invented-own-key",
        requestor_email="o@nw.example",
        customer_name="NW",
    )
    services.ensure_platform_accounts()
    services.ensure_default_connections(realm)
    mtn = Connection.objects.in_realm(realm).filter(connector_key="mtn")
    assert [(c.name, c.credentials) for c in mtn] == [("Our MTN", "own")]


def test_removing_a_key_from_env_makes_it_unavailable(env_accounts, realm, api):
    services.ensure_platform_accounts()
    services.ensure_default_connections(realm)
    env_accounts.INTEGRATIONS_PLATFORM_ACCOUNTS = {
        **env_accounts.INTEGRATIONS_PLATFORM_ACCOUNTS,
        "mtn": {"secrets": {"api_key": ""}, "settings": {}},
    }
    mtn = next(
        c for c in api.get("/api/integrations/connections/").json() if c["connector_key"] == "mtn"
    )
    assert mtn["health_error"] == services.PLATFORM_UNAVAILABLE


def test_staff_can_limit_an_account_to_granted_companies(env_accounts, realm, api):
    services.ensure_platform_accounts()
    PlatformAccount.objects.filter(env_key="vodacom").update(available_to_all=False)
    services.ensure_default_connections(realm)
    assert not Connection.objects.in_realm(realm).filter(connector_key="vodacom").exists()
    services.grant_platform_account(realm, PlatformAccount.objects.get(env_key="vodacom"))
    assert Connection.objects.in_realm(realm).filter(connector_key="vodacom").exists()


def test_viewers_see_the_providers_but_cant_override(env_accounts, realm):
    services.ensure_platform_accounts()
    services.ensure_default_connections(realm)
    mtn = Connection.objects.in_realm(realm).get(connector_key="mtn")
    pm = client_for(member(realm, "pm@example.com", "project_manager").user, realm)
    assert pm.get("/api/integrations/connections/").status_code == 200
    assert (
        pm.patch(
            f"/api/integrations/connections/{mtn.id}/", {"credentials": "own"}, format="json"
        ).status_code
        == 403
    )


# --- Herotel and Link Africa, from Rapid ----------------------------------------------------------


def test_herotels_answers_become_ours():
    connector = build_connector(spec_of("herotel"), {}, {"api_key": KEY})
    products, _ = connector.list_products()
    assert [(p.code, p.product_type.value) for p in products] == [
        ("herotelbusiness", "fibre"),
        ("herotelfttbnearnet", "fibre"),
        ("herotelwirelessbusiness", "fixed_wireless"),
    ]
    with respx.mock() as router:
        route = router.get("https://coverage.herotel.com:8096/api/Feasibility/HerotelOnly").mock(
            return_value=httpx.Response(
                200,
                json={
                    "OnNet_MapKey": [
                        {
                            "MapKey": "herotelfttbnearnet",
                            "NetworkOperatorName": "Herotel FTTB Near Net",
                            "NetworkStatus": "live",
                        }
                    ]
                },
            )
        )
        outcome = connector.check(
            [site("a", -33.97, 22.48)], [ProductRef(p.code, p.name) for p in products]
        )
    request = route.calls[0].request
    assert request.headers["api-key"] == KEY
    assert request.url.params["latitude"] == "-33.97"
    assert {a.product_code: a.status for a in outcome.answers} == {
        "herotelbusiness": Status.NOT_AVAILABLE,
        "herotelfttbnearnet": Status.NEAR_NET,
        "herotelwirelessbusiness": Status.NOT_AVAILABLE,
    }


def test_link_africas_answers_become_ours():
    connector = build_connector(
        spec_of("link_africa"), {"bandwidth_mbps": "20", "term_months": "24"}, {"api_key": KEY}
    )
    products, _ = connector.list_products()
    assert [(p.code, p.product_type.value) for p in products] == [("link_africa_fibre", "fibre")]
    refs = [ProductRef(p.code, p.name) for p in products]
    with respx.mock() as router:
        route = router.get("https://api.linkafrica.28east.co.za/getfeasibility").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        "success": True,
                        "feasible": True,
                        "bandwidth": 20,
                        "products": [{"product": "Fibre 20"}],
                    },
                ),
                httpx.Response(200, json={"success": True, "feasible": False}),
            ]
        )
        yes = connector.check([site("a", -26.1, 28.0)], refs).answers
        no = connector.check([site("b", -32.0, 24.5)], refs).answers
    params = route.calls[0].request.url.params
    assert (params["key"], params["bandwidth"], params["term"]) == (KEY, "20", "24")
    assert [(a.status, a.variant_name, a.bandwidths) for a in yes] == [
        (Status.AVAILABLE, "Fibre 20", [(20, 20)])
    ]
    assert [a.status for a in no] == [Status.NOT_AVAILABLE]


def test_a_provider_that_isnt_answering_says_so(env_accounts, realm, api, providers):
    providers.mtn.status = 503
    services.ensure_platform_accounts()
    services.ensure_default_connections(realm)
    mtn = next(
        c for c in api.get("/api/integrations/connections/").json() if c["connector_key"] == "mtn"
    )
    assert (mtn["health"], mtn["health_error"]) == ("unknown", services.PLATFORM_NOT_ANSWERING)
    assert mtn["health_checked_at"] is not None
