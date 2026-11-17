from rest_framework import serializers

from apps.realms.access import RealmScopedInputSerializer
from apps.realms.models import RealmMembership, Role


class RoleRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "key", "name"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """A user of the company, as User management shows them. `id` is the membership's id,
    which only means something inside this company."""

    email = serializers.CharField(source="user.email", read_only=True)
    role = RoleRefSerializer(read_only=True)
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = RealmMembership
        fields = ["id", "email", "name", "role", "status", "is_me", "joined_at"]
        read_only_fields = fields

    def get_is_me(self, membership) -> bool:
        request = self.context.get("request")
        return bool(request and membership.user_id == request.user.id)


class AddUserSerializer(RealmScopedInputSerializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=150)
    # Narrowed to the request's company by RealmScopedInputSerializer.
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())


class UpdateUserSerializer(RealmScopedInputSerializer):
    """Only what is sent changes. Email is never editable."""

    name = serializers.CharField(max_length=150, required=False)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)


class AcceptSerializer(serializers.Serializer):
    password = serializers.CharField(
        required=False, allow_blank=True, write_only=True, trim_whitespace=False
    )
