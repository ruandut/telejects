from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.realms.access_control import PERMISSIONS
from apps.realms.models import RealmMembership
from apps.realms.permissions import resolve_membership

from .serializers import EmailTokenObtainPairSerializer


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
        "role": {"id": role.id, "key": role.key, "name": role.name},
        "permissions": sorted(code for code in PERMISSIONS if membership.has_perm(code)),
    }
