from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("integration-logs", views.LogViewSet, basename="integration-log")

urlpatterns = router.urls
