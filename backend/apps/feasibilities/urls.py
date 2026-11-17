from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("feasibilities/runs", views.RunViewSet, basename="feasibility-run")

urlpatterns = router.urls
