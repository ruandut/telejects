from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("integrations/connectors", views.ConnectorViewSet, basename="connector")
router.register("integrations/connections", views.ConnectionViewSet, basename="connection")

urlpatterns = router.urls
