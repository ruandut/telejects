"""Rapid's paths, unchanged, so its clients only change the host (0006)."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("connect-product", views.ConnectProductViewSet, basename="connect-product")
router.register("product", views.ProductViewSet, basename="catalogue-product")

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
    *router.urls,
]
