"""What the API shows of integrations. Secrets never leave: a connection says only which secret
fields are set."""

from rest_framework import serializers

from apps.integration_logs.models import IntegrationLog
from apps.realms.access import RealmScopedSerializer

from . import services
from .canonical import PRODUCT_TYPE_LABELS
from .models import Connection, ConnectorDefinition, ProviderProduct, SyncRun


def connector_data(definition: ConnectorDefinition, granted: set[str] = frozenset()) -> dict:
    spec = definition.parsed
    return {
        # The company may use Telejects' account for this provider (0004).
        "included": spec.key in granted,
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
    # The sync's last log entry, while the log still keeps it (0005).
    log = serializers.SerializerMethodField()

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
            "log",
        ]
        read_only_fields = fields

    def get_log(self, obj):
        return (
            IntegrationLog.objects.in_realm(obj.realm_id)
            .filter(sync_id=obj.id)
            .newest()
            .values_list("id", flat=True)
            .first()
        )


class ConnectionSerializer(RealmScopedSerializer):
    """A platform connection (0004) shows none of Telejects' account: no settings, no secrets,
    and its health only as "connected" or "failing", in our words, not the provider's."""

    connector_name = serializers.SerializerMethodField()
    settings = serializers.SerializerMethodField()
    secrets_set = serializers.SerializerMethodField()
    health = serializers.SerializerMethodField()
    health_error = serializers.SerializerMethodField()
    health_checked_at = serializers.SerializerMethodField()
    can_use_platform = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    last_sync = serializers.SerializerMethodField()

    class Meta:
        model = Connection
        fields = [
            "id",
            "name",
            "connector_key",
            "connector_name",
            "credentials",
            "can_use_platform",
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

    def _granted(self) -> set[str]:
        if "_granted" not in self.context:
            realm = self.realm
            self.context["_granted"] = services.granted_connectors(realm) if realm else set()
        return self.context["_granted"]

    def _account(self, obj):
        """The platform account behind a platform connection, if it's still granted."""
        return services.granted_account(obj) if obj.uses_platform else None

    def get_can_use_platform(self, obj):
        return obj.connector_key in self._granted()

    def get_settings(self, obj):
        return {} if obj.uses_platform else obj.settings

    def get_secrets_set(self, obj):
        return [] if obj.uses_platform else sorted(obj.secret_keys_set)

    def get_health(self, obj):
        if not obj.uses_platform:
            return obj.health
        account = self._account(obj)
        return account.health if account else Connection.Health.FAILING

    def get_health_error(self, obj):
        if not obj.uses_platform:
            return obj.health_error
        account = self._account(obj)
        if account is None:
            return services.PLATFORM_UNAVAILABLE
        if account.health == Connection.Health.FAILING:
            return services.PLATFORM_FAILING
        # Checked, but not refused: the provider itself didn't answer (an outage, a 503).
        return services.PLATFORM_NOT_ANSWERING if account.health_error else ""

    def get_health_checked_at(self, obj):
        if not obj.uses_platform:
            return obj.health_checked_at
        account = self._account(obj)
        return account.health_checked_at if account else None

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
    # Switch between the company's own account and Telejects' (0004).
    credentials = serializers.ChoiceField(choices=["own", "platform"], required=False)


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
