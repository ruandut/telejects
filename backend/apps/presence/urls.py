from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("presence", views.PresenceViewSet, basename="presence")

urlpatterns = router.urls
