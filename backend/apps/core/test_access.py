"""Every /api/ route needs a signed-in user unless it is listed here, with a reason.

Don't extend the list to make this pass; give the endpoint a permission class instead.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

PUBLIC = {
    "api/health/": "liveness check, no data",
    "api/auth/token/": "signing in",
    "api/auth/token/refresh/": "refreshing a session; the refresh token is the credential",
}


def _api_routes(patterns=None, prefix=""):
    for entry in patterns if patterns is not None else get_resolver().url_patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _api_routes(entry.url_patterns, route)
        elif isinstance(entry, URLPattern) and route.startswith("api/"):
            yield route, entry.callback


def _permission_classes(callback):
    view = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    return list(getattr(view, "permission_classes", []))


def test_public_routes_exist():
    routes = {route for route, _ in _api_routes()}
    assert set(PUBLIC) <= routes


@pytest.mark.parametrize("route,callback", list(_api_routes()))
def test_route_is_signed_in_or_listed(route, callback):
    if route in PUBLIC:
        return
    perms = _permission_classes(callback)
    assert perms and AllowAny not in perms, f"{route} is open but not listed"


@pytest.mark.django_db
def test_me_needs_sign_in():
    assert APIClient().get("/api/auth/me/").status_code == 401
