import re
import secrets

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as outbox
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.realms.access_control import ADMIN
from apps.realms.services import add_member, create_realm

# Generated per test run, so not even a throwaway password is written in the repo.
TEST_PASSWORD = secrets.token_urlsafe(16)
# For confirming an invitation: a strong password, also generated per run.
NEW_PASSWORD = secrets.token_urlsafe(18)


def make_user(email: str):
    return get_user_model().objects.create_user(email=email, password=TEST_PASSWORD)


def member(realm, email: str, role_key: str = "viewer", name: str = ""):
    """An active user of `realm` with that built-in role (an existing account is reused)."""
    users = get_user_model().objects
    user = users.filter(email=email).first() or make_user(email)
    return add_member(realm, user, role_key, name=name)


def client_for(user, realm=None) -> APIClient:
    """An API client signed in as `user`, optionally naming the company its requests work in."""
    client = APIClient()
    client.force_authenticate(user)
    if realm is not None:
        client.credentials(HTTP_X_REALM=str(realm.id))
    return client


def sent_token(to: str) -> str:
    """The token in the last invitation email sent to `to`."""
    for message in reversed(outbox.outbox):
        if to in message.to:
            return re.search(r"token=([\w-]+)", message.body).group(1)
    raise AssertionError(f"No email to {to}")


@pytest.fixture(autouse=True)
def _mail_sent_inline(monkeypatch):
    """Emails go straight to Django's test outbox instead of through Hatchet."""
    from apps.accounts import mail as account_mail
    from apps.accounts import services as account_services
    from apps.users import mail, services

    monkeypatch.setattr(services, "_after_commit", lambda func: func())
    monkeypatch.setattr(mail, "enqueue_invitation", mail.deliver_invitation)
    monkeypatch.setattr(account_services, "_after_commit", lambda func: func())
    monkeypatch.setattr(
        account_services, "enqueue_password_changed", account_mail.deliver_password_changed
    )


@pytest.fixture(autouse=True)
def _fresh_throttles():
    """Throttle counters live in the cache; don't let one test's sign-ins count against another."""
    cache.clear()


@pytest.fixture
def user(db):
    return make_user("tester@example.com")


@pytest.fixture
def realm(user):
    """Northwind Fibre, where the tester is the only Admin."""
    realm = create_realm("Northwind Fibre")
    add_member(realm, user, ADMIN, name="Tess Tester")
    return realm


@pytest.fixture
def api(user, realm):
    return client_for(user, realm)


# --- integrations and feasibilities (0003): Hatchet work runs inline ---------------------------


class Worker:
    """Stands in for Hatchet. By default a new run is planned and every check runs at once;
    `hold()` leaves checks pending so a test can run them one by one with `run_check(id)`."""

    def __init__(self):
        self.held = False
        self.planned: list[int] = []

    def hold(self):
        self.held = True

    def plan(self, realm_id, run_id):
        from apps.feasibilities import services

        ids = services.plan_run(realm_id, run_id)
        self.planned += ids
        if not self.held:
            for check_id in ids:
                services.perform_check(realm_id, check_id)

    def checks(self, realm_id, run_id, check_ids):
        from apps.feasibilities import services

        if not self.held:
            for check_id in check_ids:
                services.perform_check(realm_id, check_id)


@pytest.fixture(autouse=True)
def worker(monkeypatch, settings):
    from apps.feasibilities import services as feasibilities
    from apps.integrations import services as integrations
    from apps.integrations.connectors import demo

    inline = Worker()
    monkeypatch.setattr(integrations, "_after_commit", lambda func: func())
    monkeypatch.setattr(integrations, "_enqueue", integrations.run_operation)
    monkeypatch.setattr(feasibilities, "_after_commit", lambda func: func())
    monkeypatch.setattr(feasibilities, "_enqueue_plan", inline.plan)
    monkeypatch.setattr(feasibilities, "_enqueue_checks", inline.checks)
    monkeypatch.setattr(feasibilities, "_sleep", lambda seconds: None)
    monkeypatch.setattr(demo, "DELAY_SECONDS", 0)
    # One-site checks (0006): each provider call runs inline as it is enqueued.
    from apps.site_checks import services as site_checks

    def run_calls(realm_id, call_ids):
        for call_id in call_ids:
            site_checks.perform_call(realm_id, call_id)

    monkeypatch.setattr(site_checks, "_after_commit", lambda func: func())
    monkeypatch.setattr(site_checks, "_enqueue_calls", run_calls)
    monkeypatch.setattr(site_checks, "_sleep", lambda seconds: None)
    settings.INTEGRATIONS_DEMO_ENABLED = True
    # No Telejects provider accounts unless a test sets them up: never the real keys in .env.
    settings.INTEGRATIONS_PLATFORM_ACCOUNTS = {}
    return inline


@pytest.fixture
def connectors(db):
    """The built-in connector definitions (Demo, MTN, Vodacom)."""
    from apps.integrations.services import load_definitions

    return load_definitions()


# --- invented provider APIs (respx). No real provider is ever called in tests. -----------------

MTN_URL = (
    "https://tfls-feasibility-api.mtnbusiness.co.za/api/v1/feasibility/product/solution_partner"
)
VODACOM_URL = "https://vodacom-feasibility-api.afrigis.co.za/v2"


class FakeMtn:
    """MTN's API as we understand it: products by name, many sites per call, answers in order."""

    products = ["Business Fibre 100", "Business Wireless 20", "Business LTE"]

    def __init__(self, router):
        self.not_feasible: set[str] = set()  # latitudes (as sent) where nothing is feasible
        self.status = 200
        self.not_json = False  # answer with HTML instead of JSON
        self.feasibility_calls = []
        router.get(MTN_URL).mock(side_effect=self._products)
        router.post(MTN_URL).mock(side_effect=self._check)

    def _products(self, request):
        import httpx

        if self.status != 200:
            return httpx.Response(self.status, json={"error_message": "Refused"})
        return httpx.Response(200, json={"results": self.products})

    def _check(self, request):
        import json

        import httpx

        body = json.loads(request.content)
        self.feasibility_calls.append({"headers": dict(request.headers), "body": body})
        if self.not_json:
            return httpx.Response(200, text="<html>not json</html>")
        if self.status != 200:
            return httpx.Response(self.status, json={"error_message": "Refused"})
        outputs = []
        for site in body["inputs"]:
            no = site["latitude"] in self.not_feasible
            outputs.append(
                {
                    "latitude": float(site["latitude"]),
                    "longitude": float(site["longitude"]),
                    "product_results": [
                        {
                            "product_name": name,
                            "product_capacity": "100",
                            "product_feasible": "No" if no else "Yes",
                        }
                        for name in body["product_names"]
                    ],
                }
            )
        return httpx.Response(200, json={"outputs": outputs})


class FakeVodacom:
    """Vodacom's API as Rapid uses it: one site per call, answers per access medium."""

    products = [{"id": 3, "name": "Business Internet LTE"}, {"id": 10, "name": "Business Fibre"}]

    def __init__(self, router):
        self.down: set[str] = set()  # latitudes (as sent) that get a 503
        self.slow: set[str] = set()  # latitudes (as sent) that time out
        self.status = 200
        self.feasibility_calls = []
        router.get(f"{VODACOM_URL}/api/Products").mock(side_effect=self._products)
        router.post(f"{VODACOM_URL}/api/ProductFeasible").mock(side_effect=self._check)

    def _products(self, request):
        import httpx

        return httpx.Response(200, json=self.products)

    def _check(self, request):
        import json

        import httpx

        body = json.loads(request.content)
        self.feasibility_calls.append(body)
        if self.status != 200:
            return httpx.Response(self.status, json={})
        if body["latitude"] in self.slow:
            raise httpx.ConnectTimeout("slow")
        if body["latitude"] in self.down:
            return httpx.Response(503, text="Service unavailable")
        answers = {
            3: [
                {
                    "accessMediumId": 3,
                    "name": "Mobile LTE",
                    "coverage": True,
                    "feasible": False,
                    "status": "Pending",
                    "bandwidthGroupings": [{"name": "0-50"}],
                }
            ],
            10: [
                {
                    "accessMediumId": 20,
                    "name": "Fibre",
                    "coverage": True,
                    "feasible": True,
                    "status": "Complete",
                    "bandwidthGroupings": [{"name": "100-1000"}, {"name": "1000"}],
                },
                {
                    "accessMediumId": 21,
                    "name": "Fixed Wireless",
                    "coverage": True,
                    "feasible": False,
                    "status": "Pending",
                    "bandwidthGroupings": [],
                },
            ],
        }
        return httpx.Response(
            200,
            json={
                "requestStatus": "Complete",
                "products": [
                    {
                        "productId": pid,
                        "name": f"Product {pid}",
                        "accessMediums": answers.get(pid, []),
                    }
                    for pid in body["productIds"]
                ],
            },
        )


@pytest.fixture
def providers():
    """Fake MTN and Vodacom endpoints. Any other outbound request fails the test."""
    import respx

    with respx.mock(assert_all_called=False) as router:
        yield type(
            "Providers",
            (),
            {"mtn": FakeMtn(router), "vodacom": FakeVodacom(router), "router": router},
        )


def connect(client, connector: str, name: str = "", **fields):
    """Connect a provider through the API (tested and synced inline). Returns the response."""
    return client.post(
        "/api/integrations/connections/",
        {"connector": connector, "name": name, "fields": fields},
        format="json",
    )


def rows(*coordinates, start=2):
    """Uploaded rows for (name, latitude, longitude) tuples, from line `start`."""
    return [
        {
            "line_number": start + i,
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "row": {"Site": name, "Lat": str(lat), "Lon": str(lon)},
        }
        for i, (name, lat, lon) in enumerate(coordinates)
    ]


def start_run(client, products, sites, name="Branch rollout"):
    return client.post(
        "/api/feasibilities/runs/",
        {
            "name": name,
            "products": products,
            "rows": sites,
            "columns": ["Site", "Lat", "Lon"],
            "mapping": {"name": "Site", "latitude": "Lat", "longitude": "Lon"},
        },
        format="json",
    )
