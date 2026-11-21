"""The public API documentation: what an API client can call, and how it signs in.

The OpenAPI schema (`/api/docs/schema/`) and its Redoc page (`/api/docs/`) describe only the
endpoints an API client may use (those listing `ApiClientAuthentication`) and the token endpoint.
The rest of `/api/` is the web app's own and stays out of the public docs.
"""

from rest_framework import serializers

from .authentication import ApiClientAuthentication

# Its definition is in settings (SPECTACULAR_SETTINGS["APPEND_COMPONENTS"]).
SCHEME = "clientCredentials"


def client_endpoints_only(endpoints, **kwargs):
    """Spectacular preprocessing hook: keep what an API client can call."""
    from .views import ClientTokenView

    return [
        (path, regex, method, callback)
        for path, regex, method, callback in endpoints
        if callback.cls is ClientTokenView
        or ApiClientAuthentication in getattr(callback.cls, "authentication_classes", ())
    ]


# The scheme a client endpoint documents. Its views also take a member's JWT (the web app), which
# the public docs leave out.
CLIENT_AUTH = [{SCHEME: ["api"]}]


class Token(serializers.Serializer):
    """The token request's form."""

    grant_type = serializers.ChoiceField(choices=["client_credentials"])
    client_id = serializers.CharField(help_text="Or send the ID and secret as HTTP Basic auth.")
    client_secret = serializers.CharField()


class TokenResponse(serializers.Serializer):
    access_token = serializers.CharField(help_text="Send as `Authorization: Bearer <token>`.")
    expires_in = serializers.IntegerField(help_text="Seconds: 3600.")
    token_type = serializers.ChoiceField(choices=["Bearer"])
    scope = serializers.CharField()


class TokenError(serializers.Serializer):
    error = serializers.CharField(help_text="`invalid_client`, `unsupported_grant_type`, ...")
    error_description = serializers.CharField(required=False)
