"""Rapid's paths, unchanged, so its clients only change the host (0006); and the web app's
price book pages under `price-book/`."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("connect-product", views.ConnectProductViewSet, basename="connect-product")
router.register("product", views.ProductViewSet, basename="catalogue-product")
# The price book in the portal: the web app's own, not Rapid's paths.
router.register(
    "price-book/definitions", views.PriceDefinitionViewSet, basename="price-book-definition"
)
router.register(
    "price-book/connect-products",
    views.PriceBookConnectProductViewSet,
    basename="price-book-connect-product",
)

urlpatterns = [
    path(
        "single-site-feasibility-quote/",
        views.SingleSiteFeasibilityQuoteView.as_view(),
        name="single-site-feasibility-quote",
    ),
    path(
        "single-site-feasibility/",
        views.SingleSiteFeasibilityView.as_view(),
        name="single-site-feasibility",
    ),
    path("price-book/options/", views.PriceBookOptionsView.as_view(), name="price-book-options"),
    path(
        "price-book/export/csv/",
        views.PriceBookExportView.as_view(kind="csv"),
        name="price-book-export-csv",
    ),
    path(
        "price-book/export/pdf/",
        views.PriceBookExportView.as_view(kind="pdf"),
        name="price-book-export-pdf",
    ),
    *router.urls,
]
