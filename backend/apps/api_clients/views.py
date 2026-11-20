"""A company's API clients, and the OAuth2 token endpoint they use.

Clients are looked up through `in_realm(request.realm)`, so another company's is a 404. Seeing,
creating and revoking them needs `api_clients.manage`.
"""

from oauth2_provider.views import TokenView
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.realms.access import RealmScopedMixin
from apps.realms.access_control import PERMISSIONS
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import ApiClient
from .serializers import ApiClientSerializer, CreateApiClientSerializer


class ApiClientViewSet(
    RealmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [InRealm, HasRealmPermission("api_clients.manage")]
    queryset = ApiClient.objects.listed()
    serializer_class = ApiClientSerializer
    lookup_value_regex = r"\d+"

    def create(self, request):
        serializer = CreateApiClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client, secret = services.create_client(request.membership, **serializer.validated_data)
        data = {**ApiClientSerializer(client).data, "client_secret": secret}
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def permissions(self, request):
        """What I may give a client: what a client can use that I may do myself."""
        mine = request.membership
        return Response(
            [
                {"code": code, "label": PERMISSIONS[code]}
                for code in services.CLIENT_PERMISSIONS
                if mine.has_perm(code)
            ]
        )

    def destroy(self, request, pk=None):
        client = services.revoke_client(self.get_object())
        return Response(ApiClientSerializer(client).data)


class ClientTokenView(APIView):
    """OAuth2 client credentials: a client's id and secret for an access token (an hour).

    Before sign-in, so not company-gated; the token names the client's company."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "oauth"

    def post(self, request):
        return TokenView.as_view()(request._request)
