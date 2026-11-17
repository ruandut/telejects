from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("users/invitations/<str:token>/", views.invitation, name="user-invitation"),
    *router.urls,
]
