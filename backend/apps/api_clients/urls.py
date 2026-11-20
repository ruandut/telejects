from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("api-clients", views.ApiClientViewSet, basename="api-client")

urlpatterns = [
    path("oauth/token/", views.ClientTokenView.as_view(), name="oauth_token"),
    *router.urls,
]
