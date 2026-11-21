"""Rapid's client endpoints, at Rapid's paths, with Rapid's bodies and responses (0006).

Both API clients (OAuth2) and signed-in members (JWT) may call them, inside one company:
`InRealm` takes it from the client's token, or from X-Realm for a member. Checking needs
`feasibilities.run`; anything that reads the price book needs `feasibilities.quote` and the book
offered to the company.
"""

import logging
from datetime import date

from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.api_clients.authentication import ApiClientAuthentication
from apps.api_clients.openapi import CLIENT_AUTH
from apps.realms.permissions import HasRealmPermission, InRealm

from . import books, services
from . import openapi as docs
from .models import CatalogueProduct, ConnectProduct, PriceBook, PriceDefinition
from .serializers import (
    ConnectProductInput,
    PriceDefinitionInput,
    SingleSiteFeasibilityQuoteSerializer,
    SingleSiteFeasibilitySerializer,
)

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

    def get_paginated_response_schema(self, schema):
        """For the docs, in OpenAPI 3.1 (DRF's uses 3.0's `nullable`)."""
        link = {"type": ["string", "null"], "format": "uri"}
        return {
            "type": "object",
            "required": ["count", "next", "previous", "results"],
            "properties": {
                "count": {"type": "integer", "example": 42},
                "next": {**link, "example": None},
                "previous": {**link, "example": None},
                "results": schema,
            },
        }


def _who(request) -> dict:
    client = getattr(request.user, "api_client", None)
    if client is not None:
        return {"user": None, "client_id": client.id}
    return {"user": request.user, "client_id": None}


def _failed(error: Exception):
    logger.exception("One-site check failed")
    return ValidationError({"error": f"Failed to conduct feasibility: {error}"})


@extend_schema_view(
    post=extend_schema(
        operation_id="single_site_feasibility",
        summary="Check feasibility at a place",
        description="What each provider can deliver at the coordinates. With no `products`, every "
        "product the company is connected for is checked. Waits for the providers, up to `timeout` "
        "seconds (5 to 50, default 50); a provider that fails or doesn't answer in time is listed "
        "in `exceptions`.\n\nNeeds the `feasibilities.run` permission.",
        tags=["Feasibility"],
        auth=CLIENT_AUTH,
        request=SingleSiteFeasibilitySerializer,
        responses={200: docs.SingleSiteResponse, 400: docs.FailedCheck, **docs.ERRORS},
        examples=[*docs.SINGLE_SITE_REQUEST, *docs.example("single_site")],
    )
)
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


@extend_schema_view(
    post=extend_schema(
        operation_id="single_site_feasibility_quote",
        summary="Quote at a place",
        description="Checks feasibility at the coordinates, then prices what is feasible from "
        "Telejects' price book, grouped by connect product. With no `connect_products`, every one "
        "offered is quoted. Prices are indications, not a formal quote.\n\nNeeds the "
        "`feasibilities.run` and `feasibilities.quote` permissions, and the price book offered to "
        "the company.",
        tags=["Feasibility"],
        auth=CLIENT_AUTH,
        request=SingleSiteFeasibilityQuoteSerializer,
        responses={200: docs.QuoteResponse, 400: docs.FailedCheck, **docs.ERRORS},
        examples=[*docs.QUOTE_REQUEST, *docs.example("quote")],
    )
)
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


@extend_schema_view(
    list=extend_schema(
        operation_id="connect_product_list",
        summary="List connect products",
        description="What a quote can be asked for, 20 a page. Needs `feasibilities.quote`.",
        parameters=[docs.SEARCH],
        responses={200: docs.ConnectProductData(many=True), **docs.ERRORS},
        examples=docs.page_example("connect_products"),
    ),
    retrieve=extend_schema(
        operation_id="connect_product_retrieve",
        summary="Get a connect product",
        description="Needs `feasibilities.quote`.",
        parameters=[docs.ID],
        responses={200: docs.ConnectProductData, 404: docs.Detail, **docs.ERRORS},
    ),
)
@extend_schema(tags=["Price book"], auth=CLIENT_AUTH)
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


@extend_schema_view(
    list=extend_schema(
        operation_id="product_list",
        summary="List provider products",
        description="The products a feasibility check can name, 20 a page. Needs "
        "`feasibilities.run`.",
        parameters=[docs.SEARCH, docs.PROVIDER],
        responses={200: docs.CatalogueProductData(many=True), **docs.ERRORS},
    ),
    retrieve=extend_schema(
        operation_id="product_retrieve",
        summary="Get a provider product",
        description="Needs `feasibilities.run`.",
        parameters=[docs.ID],
        responses={200: docs.CatalogueProductData, 404: docs.Detail, **docs.ERRORS},
    ),
)
@extend_schema(tags=["Price book"], auth=CLIENT_AUTH)
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


# --- the price book in the portal -----------------------------------------------------------------
# Rapid's price book admin page, for the web app only (JWT, not client tokens, and not in the API
# docs). Platform staff keep the book here; a member who may quote reads what their company is
# offered, the same as the quote endpoint prices from.


def _staff(request) -> bool:
    return bool(request.user.is_staff)


class PriceBookAccess(BasePermission):
    """Reading: platform staff, or a member with `feasibilities.quote` whose company is offered
    the book. Changing it: platform staff alone."""

    message = "Only Telejects staff can change the price book."

    def has_permission(self, request, view):
        if _staff(request):
            return True
        if request.method not in SAFE_METHODS:
            return False
        if not request.membership.has_perm("feasibilities.quote"):
            self.message = "You don't have permission to see the price book."
            return False
        if not PriceBook.objects.offered_to(request.realm.id).exists():
            self.message = PriceBookOffered.message
            return False
        return True


BOOK = [IsAuthenticated, InRealm, PriceBookAccess]


class BookPagination(PageNumberPagination):
    """Rapid's price book page: 100 a page."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


def _definitions(request):
    if _staff(request):
        return PriceDefinition.objects.all()
    return PriceDefinition.objects.offered_to(request.realm.id)


def _connect_products(request):
    if _staff(request):
        return ConnectProduct.objects.all()
    return ConnectProduct.objects.offered_to(request.realm.id)


class PriceDefinitionViewSet(viewsets.ViewSet):
    """Rapid's `/api/connect-product-definition/`: every price, newest first, searched and
    filtered by provider, medium and product."""

    permission_classes = BOOK
    lookup_value_regex = r"\d+"

    def _queryset(self):
        params = self.request.query_params
        return (
            _definitions(self.request)
            .search(params.get("search_string", ""))
            .filtered(
                provider=params.get("provider"),
                medium=params.get("medium"),
                product=params.get("product"),
            )
            .select_related("product", "access_medium")
            .prefetch_related(
                Prefetch(
                    "connect_products",
                    queryset=_connect_products(self.request).order_by("id"),
                    to_attr="visible_connect_products",
                )
            )
            .order_by("-id")
        )

    def _get(self, pk):
        definition = self._queryset().filter(pk=pk).first()
        if definition is None:
            raise Http404
        return definition

    def _data(self, definition):
        return services.definition_data(definition, definition.visible_connect_products)

    def list(self, request):
        paginator = BookPagination()
        page = paginator.paginate_queryset(self._queryset(), request, view=self)
        return paginator.get_paginated_response([self._data(d) for d in page])

    def retrieve(self, request, pk=None):
        return Response(self._data(self._get(pk)))

    def _save(self, request, definition=None):
        serializer = PriceDefinitionInput(instance=definition, data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        connect_products = values.pop("connect_products", None)
        saved = services.save_definition(definition, values, connect_products)
        return self._get(saved.pk)

    def create(self, request):
        return Response(self._data(self._save(request)), status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        return Response(self._data(self._save(request, self._get(pk))))

    def destroy(self, request, pk=None):
        services.delete_definition(self._get(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PriceBookConnectProductViewSet(viewsets.ViewSet):
    """Rapid's "Manage products": the connect products, each with how many prices it has."""

    permission_classes = BOOK
    lookup_value_regex = r"\d+"

    def _queryset(self):
        return _connect_products(self.request).order_by("name", "id")

    def _get(self, pk):
        found = self._queryset().filter(pk=pk).first()
        if found is None:
            raise Http404
        return found

    def _data(self, connect_product):
        visible = _definitions(self.request).filter(connect_products=connect_product)
        return {
            "id": connect_product.id,
            "name": connect_product.name,
            "description": connect_product.description,
            "definition_count": visible.count(),
        }

    def list(self, request):
        return Response([self._data(c) for c in self._queryset()])

    def retrieve(self, request, pk=None):
        return Response(self._data(self._get(pk)))

    def _save(self, request, connect_product=None):
        serializer = ConnectProductInput(instance=connect_product, data=request.data)
        serializer.is_valid(raise_exception=True)
        return services.save_connect_product(connect_product, dict(serializer.validated_data))

    def create(self, request):
        return Response(self._data(self._save(request)), status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        return Response(self._data(self._save(request, self._get(pk))))

    def destroy(self, request, pk=None):
        services.delete_connect_product(self._get(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PriceBookOptionsView(APIView):
    """What the price book's filters and forms choose from."""

    permission_classes = BOOK

    def get(self, request):
        return Response({**services.options_data(), "can_edit": _staff(request)})


class PriceBookExportView(APIView):
    """Rapid's `generate-pricebook-csv` and `-pdf`: staff get the whole book, a member what
    their company is offered."""

    permission_classes = BOOK
    kind = "csv"

    def get(self, request):
        definitions = None if _staff(request) else _definitions(request)
        name = f"pricebook_{date.today():%Y%m%d}.{self.kind}"
        if self.kind == "pdf":
            response = HttpResponse(books.export_pdf(definitions), content_type="application/pdf")
        else:
            response = HttpResponse(books.export_csv(definitions), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
