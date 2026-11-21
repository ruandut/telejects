"""Feasibility runs. Everything is inside the request's company: runs, sites and results are
looked up through `in_realm(request.realm)`, so another company's run is a 404, and the products
a run may use are narrowed to the company's own. Seeing needs `feasibilities.view`; starting,
renaming, pausing, continuing, cancelling, retrying and running again need `feasibilities.run`."""

import csv
import io

from django.http import HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.integrations.canonical import STATUS_LABELS
from apps.integrations.models import ProviderProduct
from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import FeasibilityRun, RunSite
from .pagination import SitePagination
from .serializers import (
    RenameRunSerializer,
    RerunSerializer,
    RunListSerializer,
    RunProductSerializer,
    RunSerializer,
    SiteSerializer,
    StartRunSerializer,
)


class RunViewSet(
    RealmScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [
        InRealm,
        HasRealmPermission("feasibilities.view", write="feasibilities.run"),
    ]
    queryset = FeasibilityRun.objects.listed()
    serializer_class = RunSerializer
    lookup_value_regex = r"\d+"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        return RunListSerializer if self.action == "list" else RunSerializer

    def get_queryset(self):
        return super().get_queryset().prefetch_related("products__connection")

    def create(self, request):
        serializer = StartRunSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        run = services.start_run(
            request.realm,
            request.user,
            name=data["name"],
            products=data["products"],
            rows=data["rows"],
            columns=data.get("columns"),
            mapping=data.get("mapping"),
        )
        fresh = self.get_queryset().get(pk=run.pk)
        return Response(
            RunSerializer(fresh, context=self.get_serializer_context()).data, status=201
        )

    def partial_update(self, request, pk=None):
        """Renames a run; its name is the only thing that can be changed."""
        run = self.get_object()
        serializer = RenameRunSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return self._fresh(services.rename_run(run, serializer.validated_data["name"]))

    def _fresh(self, run):
        return Response(
            RunSerializer(
                self.get_queryset().get(pk=run.pk), context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._fresh(services.cancel_run(self.get_object()))

    @action(detail=True, methods=["post"], url_path="retry-failed")
    def retry_failed(self, request, pk=None):
        return self._fresh(services.retry_failed(self.get_object()))

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return self._fresh(services.pause_run(self.get_object()))

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return self._fresh(services.resume_run(self.get_object()))

    @action(detail=True, methods=["post"])
    def rerun(self, request, pk=None):
        """Runs a finished run again; with `products`, against those instead (editing them)."""
        run = self.get_object()
        serializer = RerunSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        return self._fresh(services.rerun(run, serializer.validated_data.get("products")))

    @action(detail=True, methods=["get"])
    def sites(self, request, pk=None):
        """The run's sites with their results: a page (?page=, ?page_size= of 20, 50, 100 or
        200), or the ones a live event named (?ids=)."""
        run = self.get_object()
        sites = RunSite.objects.in_realm(request.realm).of_run(run)
        ids = request.query_params.get("ids")
        if ids:
            wanted = [int(i) for i in ids.split(",") if i.strip().isdigit()][
                : SitePagination.max_page_size
            ]
            sites = sites.filter(id__in=wanted)
        if state := request.query_params.get("state"):
            sites = sites.with_state(state)
        if search := request.query_params.get("search", "").strip():
            sites = sites.filter(name__icontains=search[:100])
        paginator = SitePagination()
        rows = paginator.paginate_queryset(sites.with_results(), request, view=self)
        context = self.get_serializer_context()
        return paginator.get_paginated_response(
            SiteSerializer(rows, many=True, context=context).data
        )

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        run = self.get_object()
        sites = RunSite.objects.in_realm(request.realm).of_run(run).with_results()
        content = export_csv(run, sites)
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        filename = "".join(c if c.isalnum() or c in "-_ " else "_" for c in run.name).strip()
        response["Content-Disposition"] = f'attachment; filename="{filename or "feasibility"}.csv"'
        return response

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[InRealm, HasRealmPermission("feasibilities.run")],
    )
    def products(self, request):
        """What a new run can use: the company's current products, from enabled connections."""
        products = ProviderProduct.objects.in_realm(request.realm).current().listed()
        return Response(
            RunProductSerializer(products, many=True, context=self.get_serializer_context()).data
        )


SAFE_START = ("=", "+", "@", "\t", "\r")


def _cell(value) -> str:
    """No formulas: a spreadsheet must not run a cell that came from an upload."""
    text = "" if value is None else str(value)
    if text.startswith(SAFE_START) or (text.startswith("-") and not _is_number(text)):
        return "'" + text
    return text


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def export_csv(run: FeasibilityRun, sites) -> str:
    """The uploaded columns in their order, then one column per product (and variant, such as
    Vodacom's access media), then the errors."""
    sites = list(sites)
    products = list(
        run.products.all().select_related("connection").order_by("connection__name", "name", "id")
    )
    variants: dict[int, list[str]] = {p.id: [] for p in products}
    for site in sites:
        for result in site.results.all():
            names = variants.setdefault(result.product_id, [])
            if result.variant_name and result.variant_name not in names:
                names.append(result.variant_name)
    columns = []
    for product in products:
        label = f"{product.connection.name}: {product.name}"
        names = sorted(variants.get(product.id) or [])
        if not names:
            columns.append((product.id, None, label))
        columns += [(product.id, name, f"{label} - {name}") for name in names]

    uploaded = list(run.columns) or ["Name", "Latitude", "Longitude"]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Line", *map(_cell, uploaded), *(c[2] for c in columns), "Errors"])
    serializer = SiteSerializer()
    for site in sites:
        state = serializer.get_state(site)
        found = {}
        for result in site.results.all():
            found[(result.product_id, result.variant_name or None)] = STATUS_LABELS.get(
                result.status, result.status
            )
            found.setdefault(
                (result.product_id, None), STATUS_LABELS.get(result.status, result.status)
            )
        failed = {e["connection"] for e in serializer.get_errors(site)}
        row = (
            site.row
            if run.columns
            else {
                "Name": site.name,
                "Latitude": str(site.latitude),
                "Longitude": str(site.longitude),
            }
        )
        cells = []
        by_id = {p.id: p for p in products}
        for product_id, variant, _label in columns:
            value = found.get((product_id, variant))
            if value is None and variant is not None and (product_id, None) in found:
                # The provider answered for this product, but not with this variant.
                value = STATUS_LABELS["not_available"]
            if value is None:
                if by_id[product_id].connection_id in failed:
                    value = "Error"
                elif state == "pending":
                    value = "Pending"
                elif state == "cancelled":
                    value = "Cancelled"
                else:
                    value = STATUS_LABELS["not_available"]
            cells.append(value)
        errors = "; ".join(
            f"{e['connection_name']}: {e['message']}" for e in serializer.get_errors(site)
        )
        writer.writerow(
            [site.line_number, *(_cell(row.get(c, "")) for c in uploaded), *cells, _cell(errors)]
        )
    return out.getvalue()
