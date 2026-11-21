from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("projects/access", views.ProjectAccessViewSet, basename="project-access")
router.register("projects", views.ProjectViewSet, basename="project")

urlpatterns = router.urls
