"""Integrations: the connectors a company can use, and its own connections to providers.

Everything is inside the request's company: connections, products and syncs are looked up
through `in_realm(request.realm)`, so another company's is a 404. Reading needs
`integrations.view`; connecting, editing, testing, syncing and removing need
`integrations.manage`.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import Connection, ProviderProduct, SyncRun
from .serializers import (
    ConnectInputSerializer,
    ConnectionSerializer,
    ProviderProductSerializer,
    SyncRunSerializer,
    UpdateConnectionSerializer,
    connector_data,
)

GATE = [InRealm, HasRealmPermission("integrations.view", write="integrations.manage")]


class ConnectorViewSet(viewsets.ViewSet):
    """The connector catalogue, the same for every company (but asked for inside one)."""

    permission_classes = [InRealm, HasRealmPermission("integrations.view")]

    def list(self, request):
        return Response([connector_data(d) for d in services.available_definitions()])


class ConnectionViewSet(RealmScopedMixin, viewsets.ModelViewSet):
    permission_classes = GATE
    queryset = Connection.objects.listed()
    serializer_class = ConnectionSerializer
    lookup_value_regex = r"\d+"
    http_method_names = ["get", "post", "patch", "delete"]

    def _data(self, connection, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=connection.pk)
        return Response(self.get_serializer(fresh).data, status=code)

    def create(self, request):
        serializer = ConnectInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connection = services.connect(request.realm, **serializer.validated_data)
        return self._data(connection, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        connection = self.get_object()
        serializer = UpdateConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_connection(connection, **serializer.validated_data)
        return self._data(connection)

    def destroy(self, request, pk=None):
        deleted = services.remove_connection(self.get_object())
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"deleted": False, "detail": "Runs used it, so it was turned off."})

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        services.request_operation(self.get_object(), SyncRun.Kind.TEST_CONNECTION)
        return Response(status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        services.request_operation(self.get_object(), SyncRun.Kind.SYNC_PRODUCTS)
        return Response(status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"])
    def products(self, request, pk=None):
        connection = self.get_object()
        products = (
            ProviderProduct.objects.in_realm(request.realm).filter(connection=connection).listed()
        )
        return Response(
            ProviderProductSerializer(
                products, many=True, context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["get"])
    def syncs(self, request, pk=None):
        connection = self.get_object()
        syncs = SyncRun.objects.in_realm(request.realm).filter(connection=connection).recent()[:20]
        return Response(
            SyncRunSerializer(syncs, many=True, context=self.get_serializer_context()).data
        )
