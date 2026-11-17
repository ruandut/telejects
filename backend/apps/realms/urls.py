from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("roles", views.RoleViewSet, basename="role")

urlpatterns = router.urls
