from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from .models import User


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Sign-in by email, whatever capitalisation it was typed with."""

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        return super().validate(attrs)


def issued_before_password_change(token, user) -> bool:
    """Whether `token` was issued under a password `user` has since changed (0002)."""
    return token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password)


class RevocableTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh, but not with a token from before a password change: SimpleJWT's
    CHECK_REVOKE_TOKEN only checks access tokens, and refreshing would hand out new ones."""

    def validate(self, attrs):
        refresh = RefreshToken(attrs["refresh"])
        user = User.objects.filter(pk=refresh.get(api_settings.USER_ID_CLAIM)).first()
        if user is None or issued_before_password_change(refresh, user):
            raise AuthenticationFailed("The user's password has been changed.", "password_changed")
        return super().validate(attrs)


class PasswordChangeSerializer(serializers.Serializer):
    # Never trimmed: spaces are part of a password.
    current_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)
