"""The public API docs (/api/docs/): served signed out, limited to what an API client can call,
and held to the responses the contract tests pin down, so the docs can't drift from the API."""

from urllib.parse import urlencode

import jsonschema
import pytest
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from .openapi import rapid_response
from .test_pricebook import bearer, make_book, make_client

CLIENT_PATHS = {
    "/api/oauth/token/",
    "/api/single-site-feasibility/",
    "/api/single-site-feasibility-quote/",
    "/api/connect-product/",
    "/api/connect-product/{id}/",
    "/api/product/",
    "/api/product/{id}/",
}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def response_schema(schema, path, method="post"):
    content = schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]
    return content["schema"]


def assert_matches(schema, documented, body):
    """`body` fits the documented schema, every field present and nothing undocumented."""

    def strict(node):
        if isinstance(node, dict):
            node = {k: strict(v) for k, v in node.items()}
            if "properties" in node:
                node.setdefault("additionalProperties", False)
        elif isinstance(node, list):
            node = [strict(v) for v in node]
        return node

    root = {**documented, "components": strict(schema["components"])}
    jsonschema.Draft202012Validator(root).validate(body)


def test_the_docs_are_served_signed_out(db):
    page = APIClient().get("/api/docs/")
    assert page.status_code == 200
    assert b"redoc" in page.content.lower()
    res = APIClient().get("/api/docs/schema/", HTTP_ACCEPT="application/json")
    assert res.status_code == 200
    assert res.json()["info"]["title"] == "Telejects API"


def test_the_docs_show_only_what_an_api_client_can_call(schema):
    assert set(schema["paths"]) == CLIENT_PATHS
    assert set(schema["components"]["securitySchemes"]) == {"clientCredentials"}


def test_the_schema_builds_without_warnings(db):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null")


@pytest.mark.parametrize(
    "path, name, method",
    [
        ("/api/single-site-feasibility/", "single_site", "post"),
        ("/api/single-site-feasibility-quote/", "quote", "post"),
        ("/api/connect-product/", "connect_products", "get"),
    ],
)
def test_the_docs_describe_rapids_responses(schema, path, name, method):
    assert_matches(schema, response_schema(schema, path, method), rapid_response(name))


def test_the_docs_describe_a_token_and_a_product_page(schema, api):
    make_book()
    created = make_client(api, ["feasibilities.run"])
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
    token = res.json()
    assert_matches(schema, response_schema(schema, "/api/oauth/token/"), token)

    page = bearer(token["access_token"]).get("/api/product/")
    assert page.status_code == 200
    assert_matches(schema, response_schema(schema, "/api/product/", "get"), page.json())
