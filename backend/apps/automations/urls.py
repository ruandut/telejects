from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("automations", views.AutomationViewSet, basename="automation")

urlpatterns = router.urls
