"""What the API shows of integrations. Secrets never leave: a connection says only which secret
fields are set."""

from rest_framework import serializers

from apps.realms.access import RealmScopedSerializer

from .canonical import PRODUCT_TYPE_LABELS
from .models import Connection, ConnectorDefinition, ProviderProduct, SyncRun


def connector_data(definition: ConnectorDefinition) -> dict:
    spec = definition.parsed
    return {
        "key": spec.key,
        "name": spec.name,
        "description": spec.description,
        "capabilities": spec.capabilities,
        "version": definition.version,
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "help": f.help,
                "type": f.type,
                "required": f.required,
            }
            for f in spec.fields
        ],
    }


class SyncRunSerializer(RealmScopedSerializer):
    class Meta:
        model = SyncRun
        fields = [
            "id",
            "kind",
            "trigger",
            "outcome",
            "started_at",
            "finished_at",
            "added",
            "retired",
            "error",
        ]
        read_only_fields = fields


class ConnectionSerializer(RealmScopedSerializer):
    connector_name = serializers.SerializerMethodField()
    secrets_set = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    last_sync = serializers.SerializerMethodField()

    class Meta:
        model = Connection
        fields = [
            "id",
            "name",
            "connector_key",
            "connector_name",
            "settings",
            "secrets_set",
            "enabled",
            "health",
            "health_error",
            "health_checked_at",
            "product_count",
            "last_sync",
            "created_at",
        ]
        read_only_fields = fields

    def _definitions(self) -> dict:
        if "_definitions" not in self.context:
            self.context["_definitions"] = {d.key: d for d in ConnectorDefinition.objects.latest()}
        return self.context["_definitions"]

    def get_connector_name(self, obj):
        definition = self._definitions().get(obj.connector_key)
        return definition.parsed.name if definition else obj.connector_key

    def get_secrets_set(self, obj):
        return sorted(obj.secret_keys_set)

    def get_product_count(self, obj):
        return obj.products.filter(retired_at=None).count()

    def get_last_sync(self, obj):
        last = obj.syncs.order_by("-started_at", "-id").first()
        return SyncRunSerializer(last).data if last else None


class ConnectInputSerializer(serializers.Serializer):
    connector = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    fields = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=1000))


class UpdateConnectionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    fields = serializers.DictField(
        child=serializers.CharField(allow_blank=True, max_length=1000), required=False
    )
    enabled = serializers.BooleanField(required=False)


class ProviderProductSerializer(RealmScopedSerializer):
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    product_type_label = serializers.SerializerMethodField()

    class Meta:
        model = ProviderProduct
        fields = [
            "id",
            "connection",
            "connection_name",
            "code",
            "name",
            "product_type",
            "product_type_label",
            "retired_at",
        ]
        read_only_fields = fields

    def get_product_type_label(self, obj):
        return PRODUCT_TYPE_LABELS.get(obj.product_type, obj.product_type)
