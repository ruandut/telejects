"""What the Logs section (and its live topic) shows. The socket uses these same serializers."""

from rest_framework import serializers

from apps.realms.access import RealmScopedSerializer

from .models import IntegrationLog


class LogListSerializer(RealmScopedSerializer):
    operation_label = serializers.CharField(source="get_operation_display", read_only=True)

    class Meta:
        model = IntegrationLog
        fields = [
            "id",
            "created_at",
            "operation",
            "operation_label",
            "connection_id",
            "connection_name",
            "credentials",
            "method",
            "url",
            "status_code",
            "duration_ms",
            "outcome",
            "error",
            "attempt",
            "run_id",
            "check_id",
            "sync_id",
        ]
        read_only_fields = fields


class LogDetailSerializer(LogListSerializer):
    class Meta(LogListSerializer.Meta):
        fields = [
            *LogListSerializer.Meta.fields,
            "connector_key",
            "definition_version",
            "request_headers",
            "request_body",
            "response_headers",
            "response_body",
        ]
        read_only_fields = fields
