"""Rapid's client endpoints, at Rapid's paths, with Rapid's bodies and responses (0006).

Both API clients (OAuth2) and signed-in members (JWT) may call them, inside one company:
`InRealm` takes it from the client's token, or from X-Realm for a member. Checking needs
`feasibilities.run`; anything that reads the price book needs `feasibilities.quote` and the book
offered to the company.
"""

import logging

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.api_clients.authentication import ApiClientAuthentication
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import CatalogueProduct, ConnectProduct, PriceBook
from .serializers import SingleSiteFeasibilityQuoteSerializer, SingleSiteFeasibilitySerializer

logger = logging.getLogger(__name__)

AUTHENTICATION = [ApiClientAuthentication, JWTAuthentication]


class PriceBookOffered(BasePermission):
    message = "Telejects' price book isn't offered to this company."

    def has_permission(self, request, view):
        return PriceBook.objects.offered_to(request.realm.id).exists()


CHECK = [IsAuthenticated, InRealm, HasRealmPermission("feasibilities.run")]
QUOTE = [
    IsAuthenticated,
    InRealm,
    HasRealmPermission("feasibilities.run"),
    HasRealmPermission("feasibilities.quote"),
    PriceBookOffered,
]
READ_BOOK = [IsAuthenticated, InRealm, HasRealmPermission("feasibilities.quote"), PriceBookOffered]


class RapidPagination(PageNumberPagination):
    """Rapid's: 20 a page, `page` and `page_size`."""

    page_size = 20
    page_size_query_param = "page_size"


def _who(request) -> dict:
    client = getattr(request.user, "api_client", None)
    if client is not None:
        return {"user": None, "client_id": client.id}
    return {"user": request.user, "client_id": None}


def _failed(error: Exception):
    logger.exception("One-site check failed")
    return ValidationError({"error": f"Failed to conduct feasibility: {error}"})


class SingleSiteFeasibilityView(APIView):
    authentication_classes = AUTHENTICATION
    permission_classes = CHECK

    def post(self, request):
        serializer = SingleSiteFeasibilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        realm_id = request.realm.id
        if data.get("products"):
            products = list(CatalogueProduct.objects.filter(pk__in=data["products"]))
        else:
            products = services.connected_products(realm_id)
        try:
            body = services.single_site(
                realm_id,
                latitude=data["latitude"],
                longitude=data["longitude"],
                products=products,
                timeout=data["timeout"],
                **_who(request),
            )
        except Exception as error:
            raise _failed(error) from error
        return Response(body)


class SingleSiteFeasibilityQuoteView(APIView):
    authentication_classes = AUTHENTICATION
    permission_classes = QUOTE

    def post(self, request):
        realm_id = request.realm.id
        serializer = SingleSiteFeasibilityQuoteSerializer(
            data=request.data, context={"realm_id": realm_id}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        offered = ConnectProduct.objects.offered_to(realm_id).order_by("id")
        if data.get("connect_products"):
            offered = offered.filter(pk__in=data["connect_products"])
        try:
            body = services.quote(
                realm_id,
                latitude=data["latitude"],
                longitude=data["longitude"],
                connect_products=list(offered),
                timeout=data["timeout"],
                **_who(request),
            )
        except Exception as error:
            raise _failed(error) from error
        return Response(body)


class ConnectProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Rapid's `/api/connect-product/`: what a quote can be asked for."""

    authentication_classes = AUTHENTICATION
    permission_classes = READ_BOOK
    pagination_class = RapidPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return (
            ConnectProduct.objects.offered_to(self.request.realm.id)
            .search(self.request.query_params.get("search_string", ""))
            .prefetch_related("product_definitions__product")
            .order_by("name", "id")
        )

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([services.connect_product_data(c) for c in page])

    def retrieve(self, request, pk=None):
        return Response(services.connect_product_data(self.get_object()))


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Rapid's `/api/product/`: the provider products a single-site check can name."""

    authentication_classes = AUTHENTICATION
    permission_classes = CHECK
    pagination_class = RapidPagination
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        products = CatalogueProduct.objects.search(
            self.request.query_params.get("search_string", "")
        )
        provider = self.request.query_params.get("provider")
        if provider not in (None, ""):
            products = products.filter(provider=provider) if provider.isdigit() else products.none()
        return products.order_by("name", "id")

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([services.catalogue_product_data(p) for p in page])

    def retrieve(self, request, pk=None):
        return Response(services.catalogue_product_data(self.get_object()))
