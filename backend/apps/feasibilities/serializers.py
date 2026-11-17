"""What the API (and the live socket, live.py) shows of feasibility runs. The socket uses these
same serializers, so both always agree."""

from rest_framework import serializers

from apps.integrations.canonical import PRODUCT_TYPE_LABELS, STATUS_LABELS
from apps.integrations.models import ProviderProduct
from apps.realms.access import RealmScopedInputSerializer, RealmScopedSerializer

from .models import FeasibilityRun, ProviderCheck, RunSite


class RunProductSerializer(RealmScopedSerializer):
    connection_name = serializers.CharField(source="connection.name", read_only=True)

    class Meta:
        model = ProviderProduct
        fields = [
            "id",
            "name",
            "code",
            "product_type",
            "connection",
            "connection_name",
            "retired_at",
        ]
        read_only_fields = fields


class RunSerializer(RealmScopedSerializer):
    created_by = serializers.SerializerMethodField()
    products = RunProductSerializer(many=True, read_only=True)
    sites_finished = serializers.SerializerMethodField()

    class Meta:
        model = FeasibilityRun
        fields = [
            "id",
            "name",
            "status",
            "created_by",
            "created_at",
            "started_at",
            "finished_at",
            "site_count",
            "sites_finished",
            "checks_total",
            "checks_done",
            "checks_failed",
            "checks_cancelled",
            "columns",
            "mapping",
            "products",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by else None

    def get_sites_finished(self, obj):
        if obj.status == FeasibilityRun.Status.QUEUED:
            return 0
        return RunSite.objects.in_realm(obj.realm_id).of_run(obj).finished().count()


class RunListSerializer(RunSerializer):
    class Meta(RunSerializer.Meta):
        fields = [f for f in RunSerializer.Meta.fields if f not in ("columns", "mapping")]


class SiteSerializer(RealmScopedSerializer):
    """A site with its results per product, the errors of failed calls, and its state:
    pending (a call is still open), error, cancelled or done."""

    state = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()
    errors = serializers.SerializerMethodField()

    class Meta:
        model = RunSite
        fields = [
            "id",
            "line_number",
            "name",
            "latitude",
            "longitude",
            "state",
            "results",
            "errors",
        ]
        read_only_fields = fields

    def get_state(self, obj):
        states = {c.status for c in obj.checks.all()}
        if not states:
            # Not planned into provider calls yet (queued), or cancelled before it was.
            return "cancelled" if obj.run.status == FeasibilityRun.Status.CANCELLED else "pending"
        if states & {ProviderCheck.Status.PENDING, ProviderCheck.Status.RUNNING}:
            return "pending"
        if ProviderCheck.Status.FAILED in states:
            return "error"
        if ProviderCheck.Status.CANCELLED in states:
            return "cancelled"
        return "done"

    def get_results(self, obj):
        return [
            {
                "product": r.product_id,
                "status": r.status,
                "status_label": STATUS_LABELS.get(r.status, r.status),
                "variant_name": r.variant_name,
                "product_type": r.product_type,
                "product_type_label": PRODUCT_TYPE_LABELS.get(r.product_type, r.product_type),
                "bandwidths": r.bandwidths,
                "note": r.note,
            }
            for r in obj.results.all()
        ]

    def get_errors(self, obj):
        return [
            {
                "connection": c.connection_id,
                "connection_name": c.connection.name,
                "message": c.error,
            }
            for c in obj.checks.all()
            if c.status == ProviderCheck.Status.FAILED
        ]


class StartRunSerializer(RealmScopedInputSerializer):
    name = serializers.CharField(max_length=100)
    products = serializers.PrimaryKeyRelatedField(
        queryset=ProviderProduct.objects.all(), many=True, allow_empty=False
    )
    columns = serializers.ListField(
        child=serializers.CharField(max_length=100, allow_blank=True), required=False, max_length=50
    )
    mapping = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    # Validated row by row in services.start_run, which reports problems per line.
    rows = serializers.ListField(child=serializers.JSONField(), max_length=10_000)
