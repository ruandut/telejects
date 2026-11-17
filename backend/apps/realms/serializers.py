from rest_framework import serializers

from .access import RealmScopedSerializer
from .access_control import PERMISSIONS
from .models import Role


class RoleSerializer(RealmScopedSerializer):
    """A company's role, with what it allows, for the role picker."""

    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "key", "name", "description", "is_system", "permissions"]
        read_only_fields = fields

    def get_permissions(self, role) -> list[dict]:
        return [
            {"code": code, "label": PERMISSIONS[code]}
            for code in PERMISSIONS
            if code in role.permission_set
        ]
