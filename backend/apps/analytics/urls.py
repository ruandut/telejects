from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("analytics/dashboards", views.DashboardViewSet, basename="dashboard")
router.register("analytics/widgets", views.WidgetViewSet, basename="widget")
router.register("analytics", views.InsightsViewSet, basename="analytics")

urlpatterns = router.urls
