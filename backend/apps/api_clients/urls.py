from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("api-clients", views.ApiClientViewSet, basename="api-client")

urlpatterns = [
    path("oauth/token/", views.ClientTokenView.as_view(), name="oauth_token"),
    # The public docs: what an API client can call (openapi.py).
    path("docs/schema/", SpectacularAPIView.as_view(), name="api_docs_schema"),
    path(
        "docs/",
        SpectacularRedocView.as_view(
            url_name="api_docs_schema", template_name="api_clients/redoc.html"
        ),
        name="api_docs",
    ),
    *router.urls,
]
