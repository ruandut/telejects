from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import EmailTokenObtainPairSerializer


class SignInView(TokenObtainPairView):
    """Email + password for a JWT pair. Throttled, as it is the one place passwords are tried."""

    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


@api_view(["GET"])
def me(request):
    """Who's signed in."""
    user = request.user
    return Response({"id": user.id, "email": user.email, "name": user.display_name})
