"""User management: a company's people, and the public link that lets an invited person confirm
their account."""

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.realms.models import RealmMembership
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .serializers import AcceptSerializer, AddUserSerializer, UpdateUserSerializer, UserSerializer


class UserViewSet(viewsets.ViewSet):
    """Only inside the request's company: every lookup starts from `_users()`, which is
    `in_realm(request.realm)`, so another company's user is a 404. Reading needs `users.view`,
    changing anything `users.manage`."""

    permission_classes = [InRealm, HasRealmPermission("users.view", write="users.manage")]
    lookup_value_regex = r"\d+"

    def _users(self):
        return RealmMembership.objects.in_realm(self.request.realm).people()

    def _user(self, pk):
        membership = self._users().by_id(pk)
        if membership is None:
            raise Http404
        return membership

    def _context(self):
        return {"request": self.request, "realm": self.request.realm}

    def _data(self, membership) -> dict:
        return UserSerializer(self._users().by_id(membership.pk), context=self._context()).data

    def list(self, request):
        return Response(UserSerializer(self._users(), many=True, context=self._context()).data)

    def create(self, request):
        serializer = AddUserSerializer(data=request.data, context=self._context())
        serializer.is_valid(raise_exception=True)
        membership = services.add_user(request.realm, **serializer.validated_data)
        return Response(self._data(membership), status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(self._data(self._user(pk)))

    def partial_update(self, request, pk=None):
        membership = self._user(pk)
        serializer = UpdateUserSerializer(data=request.data, context=self._context())
        serializer.is_valid(raise_exception=True)
        services.update_user(membership, **serializer.validated_data)
        return Response(self._data(membership))

    def destroy(self, request, pk=None):
        services.remove_user(self._user(pk), request.data.get("new_admin"))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        services.resend_invitation(self._user(pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- public: confirming an account by its emailed link ----------------------------------------


def _problem(error: services.InvitationProblem) -> Response:
    code = status.HTTP_404_NOT_FOUND if error.code == "not_found" else status.HTTP_410_GONE
    return Response({"detail": str(error), "code": error.code}, status=code)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def invitation(request, token):
    """GET says what the link is for. POST confirms the account, setting a password if it's new.

    Works only for whoever holds the token, and tells them only the company's name and their
    own address.
    """
    try:
        if request.method == "GET":
            found = services.invitation_for(token)
            return Response(
                {
                    "realm_name": found.membership.realm.name,
                    "email": found.membership.user.email,
                    "needs_password": not found.membership.user.has_usable_password(),
                }
            )
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership, is_new = services.accept_invitation(
            token, serializer.validated_data.get("password")
        )
    except services.InvitationProblem as error:
        return _problem(error)
    if not is_new:
        # An existing account signs in with its own password.
        return Response({"signed_in": False, "realm_id": membership.realm_id})
    refresh = RefreshToken.for_user(membership.user)
    return Response(
        {
            "signed_in": True,
            "realm_id": membership.realm_id,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
    )


invitation.cls.throttle_scope = "invitation"
