"""The connector engine: definitions as data, run against invented provider answers."""

import json
from decimal import Decimal

import httpx
import pytest
import respx

from apps.integrations.canonical import (
    ConnectorError,
    ErrorKind,
    ProductRef,
    ProductType,
    SiteQuery,
    Status,
)
from apps.integrations.connectors import demo
from apps.integrations.engine import build_connector, parse_bandwidth
from apps.integrations.services import DEFINITIONS_DIR
from apps.integrations.spec import ConnectorSpec
from apps.integrations.templating import TemplateError, render
from conftest import MTN_URL, VODACOM_URL, FakeMtn, FakeVodacom


def spec_of(key: str) -> ConnectorSpec:
    return ConnectorSpec.model_validate_json((DEFINITIONS_DIR / f"{key}.json").read_text())


def site(ref, lat, lon):
    return SiteQuery(ref, f"Site {ref}", Decimal(str(lat)), Decimal(str(lon)))


SECRET = "invented-key-123456"


# --- templating --------------------------------------------------------------------------------


def test_templates_fill_values_and_lists_but_run_nothing():
    context = {"site": {"latitude": -26.1, "name": "Depot"}, "sites": [{"a": 1}, {"a": 2}]}
    assert render("{{ site.latitude }}", context) == -26.1
    assert render("{{ site.latitude | string }}", context) == "-26.1"
    assert render("Site {{ site.name }}", context) == "Site Depot"
    assert render({"$each": "sites", "item": {"x": "{{ item.a }}"}}, context) == [
        {"x": 1},
        {"x": 2},
    ]
    with pytest.raises(TemplateError):
        render("{{ site.__class__ }}", context)
    with pytest.raises(TemplateError):
        render("{{ secrets.api_key }}", context)


def test_bandwidths_read_like_rapids():
    assert parse_bandwidth("0-50") == (0, 50)
    assert parse_bandwidth("1000") == (1000, 1000)
    assert parse_bandwidth(20) == (20, 20)
    assert parse_bandwidth("fast") is None


# --- definitions are checked -------------------------------------------------------------------


@pytest.mark.parametrize(
    "change,message",
    [
        ({"base_url": "http://plain.example.com"}, "https://"),
        ({"python": "os.system"}, "apps.integrations.connectors."),
        ({"auth": [{"field": "nope", "location": "header", "name": "X"}]}, "isn't a secret"),
    ],
)
def test_bad_definitions_are_refused(change, message):
    data = {**json.loads((DEFINITIONS_DIR / "mtn.json").read_text()), **change}
    with pytest.raises(ValueError, match=message):
        ConnectorSpec.model_validate(data)


def test_a_bad_expression_is_refused():
    data = json.loads((DEFINITIONS_DIR / "mtn.json").read_text())
    data["feasibility"]["product"] = "product_name[["
    with pytest.raises(ValueError, match="JMESPath"):
        ConnectorSpec.model_validate(data)


# --- MTN (AT-0003-22) --------------------------------------------------------------------------


def mtn():
    return build_connector(
        spec_of("mtn"),
        {"requestor_email": "ops@northwind.example", "customer_name": "Northwind Fibre"},
        {"api_key": SECRET},
    )


def test_at_0003_22_mtns_answers_become_ours():
    with respx.mock(assert_all_called=False) as router:
        fake = FakeMtn(router)
        fake.not_feasible.add("-33.9")
        products, _ = mtn().list_products()
        assert [(p.name, p.product_type) for p in products] == [
            ("Business Fibre 100", ProductType.FIBRE),
            ("Business Wireless 20", ProductType.FIXED_WIRELESS),
            ("Business LTE", ProductType.LTE),
        ]
        refs = [ProductRef(p.code, p.name) for p in products[:2]]
        outcome = mtn().check([site("a", -26.1, 28.0), site("b", -33.9, 18.4)], refs)

    call = fake.feasibility_calls[0]
    assert call["headers"]["x-api-key"] == SECRET
    assert call["body"]["inputs"][1] == {
        "latitude": "-33.9",
        "longitude": "18.4",
        "customer_name": "Northwind Fibre",
    }
    assert call["body"]["requestor"] == "ops@northwind.example"
    by_site = {(a.site_ref, a.product_code): a for a in outcome.answers}
    assert by_site[("a", "Business Fibre 100")].status == Status.AVAILABLE
    assert by_site[("a", "Business Fibre 100")].bandwidths == [(100, 100)]
    assert by_site[("b", "Business Wireless 20")].status == Status.NOT_AVAILABLE
    # Matched by position, and the key never reaches what is recorded.
    assert SECRET not in json.dumps([c.request for c in outcome.calls])


def test_at_0003_22_mtn_errors_get_the_right_kind():
    for code, kind in [
        (401, ErrorKind.AUTH),
        (429, ErrorKind.RATE_LIMITED),
        (503, ErrorKind.PROVIDER_DOWN),
        (400, ErrorKind.BAD_REQUEST),
    ]:
        with respx.mock() as router:
            router.post(MTN_URL).mock(
                return_value=httpx.Response(code, json={"error_message": "No"})
            )
            with pytest.raises(ConnectorError) as error:
                mtn().check([site("a", -26.1, 28.0)], [ProductRef("Business LTE", "Business LTE")])
        assert error.value.kind == kind
    with respx.mock() as router:
        router.post(MTN_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
        with pytest.raises(ConnectorError) as error:
            mtn().check([site("a", -26.1, 28.0)], [ProductRef("Business LTE", "Business LTE")])
    assert error.value.kind == ErrorKind.TIMEOUT and error.value.retryable


def test_mtn_answers_that_dont_match_the_sites_are_refused():
    with respx.mock() as router:
        router.post(MTN_URL).mock(return_value=httpx.Response(200, json={"outputs": []}))
        with pytest.raises(ConnectorError) as error:
            mtn().check([site("a", -26.1, 28.0)], [ProductRef("Business LTE", "Business LTE")])
    assert error.value.kind == ErrorKind.BAD_RESPONSE


# --- Vodacom (AT-0003-23) ----------------------------------------------------------------------


def vodacom():
    return build_connector(
        spec_of("vodacom"), {"calling_system": "Northwind"}, {"auth_key": SECRET}
    )


def test_at_0003_23_vodacoms_answers_become_ours():
    with respx.mock(assert_all_called=False) as router:
        fake = FakeVodacom(router)
        products, _ = vodacom().list_products()
        refs = [ProductRef(p.code, p.name) for p in products]
        outcome = vodacom().check([site("a", -26.1, 28.0)], refs)

    body = fake.feasibility_calls[0]
    assert body["AuthKey"] == SECRET
    assert body["productIds"] == [3, 10]
    assert body["latitude"] == "-26.1"
    assert "callingBackUrl" not in body
    answers = {(a.product_code, a.variant_name): a for a in outcome.answers}
    # Covered but not feasible: coverage only. (Rapid's workaround, which counted coverage alone
    # as available for some media, is off for now.)
    assert answers[("3", "Mobile LTE")].status == Status.COVERAGE_ONLY
    assert answers[("3", "Mobile LTE")].product_type == ProductType.LTE
    fibre = answers[("10", "Fibre")]
    assert (fibre.status, fibre.variant_code, fibre.product_type) == (
        Status.AVAILABLE,
        "20",
        ProductType.FIBRE,
    )
    assert fibre.bandwidths == [(100, 1000), (1000, 1000)]
    # Covered but not feasible: shown as coverage only, not as "no".
    assert answers[("10", "Fixed Wireless")].status == Status.COVERAGE_ONLY
    assert SECRET not in json.dumps([c.request for c in outcome.calls])


def test_vodacom_product_with_no_media_is_not_available():
    with respx.mock() as router:
        router.post(f"{VODACOM_URL}/api/ProductFeasible").mock(
            return_value=httpx.Response(
                200, json={"products": [{"productId": 3, "accessMediums": []}]}
            )
        )
        outcome = vodacom().check([site("a", -26.1, 28.0)], [ProductRef("3", "LTE")])
    assert [(a.product_code, a.status) for a in outcome.answers] == [("3", Status.NOT_AVAILABLE)]


# --- shapes Herotel and Link Africa need, with no code ----------------------------------------

PRESENCE = {
    "key": "presence",
    "name": "Presence Provider",
    "base_url": "https://coverage.example.com",
    "fields": [{"key": "api_key", "label": "API key", "type": "secret"}],
    "auth": [{"field": "api_key", "location": "query", "name": "key"}],
    "products": {
        "static": [{"code": "onnet", "name": "On-net"}, {"code": "nearnet", "name": "Near-net"}],
        "code": "code",
        "name": "name",
        "default_type": "fibre",
    },
    "test_with": "feasibility",
    "feasibility": {
        "request": {"method": "GET", "path": "/check", "query": {"lat": "{{ site.latitude }}"}},
        "answers": "keys",
        "product": "@",
        "status_rules": [
            {"when": "@ == 'nearnet'", "status": "near_net"},
            {"when": "@ == 'onnet'", "status": "available"},
        ],
        "absent_status": "not_available",
    },
}


def test_a_presence_answer_and_a_query_key_need_only_a_definition():
    connector = build_connector(ConnectorSpec.model_validate(PRESENCE), {}, {"api_key": SECRET})
    with respx.mock() as router:
        route = router.get("https://coverage.example.com/check").mock(
            return_value=httpx.Response(200, json={"keys": ["nearnet"]})
        )
        products, calls = connector.list_products()
        outcome = connector.check(
            [site("a", -26.1, 28.0)], [ProductRef(p.code, p.name) for p in products]
        )
    assert calls == []
    assert route.calls[0].request.url.params["key"] == SECRET
    assert {a.product_code: a.status for a in outcome.answers} == {
        "nearnet": Status.NEAR_NET,
        "onnet": Status.NOT_AVAILABLE,
    }
    assert SECRET not in json.dumps(outcome.calls[0].request)


# --- Demo (AT-0003-24) -------------------------------------------------------------------------


def test_at_0003_24_the_demo_answers_predictably_and_sometimes_fails(monkeypatch):
    monkeypatch.setattr(demo, "DELAY_SECONDS", 0)
    connector = build_connector(spec_of("demo"), {}, {})
    products, _ = connector.list_products()
    refs = [ProductRef(p.code, p.name) for p in products]
    sites = [site(str(i), -26 - i / 1000, 28 + i / 1000) for i in range(40)]
    good = [s for s in sites if not demo.fails(s)]
    bad = [s for s in sites if demo.fails(s)]
    assert good and bad
    first = connector.check(good[:3], refs).answers
    assert first == connector.check(good[:3], refs).answers
    assert len({a.status for a in connector.check(good, refs).answers}) > 1
    with pytest.raises(ConnectorError):
        connector.check([bad[0], good[0]], refs)
    # Only a call's first site decides whether it fails.
    assert connector.check([good[0], bad[0]], refs).answers
