from rest_framework import serializers

from apps.realms.access_control import PERMISSIONS

from .models import ApiClient


class ApiClientSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    active = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = ApiClient
        fields = [
            "id",
            "name",
            "client_id",
            "permissions",
            "created_by",
            "created_at",
            "last_used_at",
            "revoked_at",
            "active",
        ]
        read_only_fields = fields

    def get_created_by(self, client) -> str:
        user = client.created_by
        return (user.display_name or user.email) if user else ""


class CreateApiClientSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=sorted(PERMISSIONS)), allow_empty=False
    )
