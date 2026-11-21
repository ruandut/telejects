from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.realms.access_control import PERMISSIONS
from apps.realms.models import RealmMembership
from apps.realms.permissions import resolve_membership

from . import services
from .serializers import EmailTokenObtainPairSerializer, PasswordChangeSerializer


class SignInView(TokenObtainPairView):
    """Email + password for a JWT pair. Throttled, as it is the one place passwords are tried."""

    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Who's signed in; the company this request works in, with my role and permissions there
    (null when there's none, or I'm not in the one asked for); and the companies I belong to.
    Never mentions any other company."""
    user = request.user
    try:
        current = resolve_membership(request)
    except PermissionDenied:
        current = None
    return Response(
        {
            "id": user.id,
            "email": user.email,
            "name": current.display_name if current else user.display_name,
            "realm": _current(current) if current else None,
            "realms": [
                {"id": m.realm_id, "name": m.realm.name}
                for m in RealmMembership.objects.of_user(user)
            ],
        }
    )


def _current(membership) -> dict:
    role = membership.role
    return {
        "id": membership.realm_id,
        "name": membership.realm.name,
        # My membership's id there: how boards name me (people columns, presence).
        "membership": membership.id,
        "role": {"id": role.id, "key": role.key, "name": role.name},
        "permissions": sorted(code for code in PERMISSIONS if membership.has_perm(code)),
    }


class PasswordThrottle(UserRateThrottle):
    """Per person, at the "password" rate."""

    scope = "password"


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([PasswordThrottle])
def change_password(request):
    """Change my own password with my current one (0002). Names no user, so it can only ever be
    mine. Throttled like sign-in, so it can't be used to guess. Other browsers are signed out;
    this one gets fresh tokens and stays signed in."""
    data = PasswordChangeSerializer(data=request.data)
    data.is_valid(raise_exception=True)
    services.change_password(
        request.user, data.validated_data["current_password"], data.validated_data["new_password"]
    )
    refresh = RefreshToken.for_user(request.user)
    return Response({"access": str(refresh.access_token), "refresh": str(refresh)})
