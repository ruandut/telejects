from rest_framework import serializers

from .models import Automation, AutomationRun


class AutomationSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Automation
        fields = [
            "id",
            "board",
            "name",
            "enabled",
            "trigger",
            "conditions",
            "actions",
            "delay",
            "created_by_name",
            "created_at",
            "updated_at",
            "run_count",
            "last_run_at",
        ]
        read_only_fields = fields

    def get_created_by_name(self, automation) -> str | None:
        return automation.created_by.display_name if automation.created_by_id else None


class RunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutomationRun
        fields = [
            "id",
            "item",
            "item_name",
            "status",
            "message",
            "due_at",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields


class AutomationInputSerializer(serializers.Serializer):
    board = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=120, required=False)
    enabled = serializers.BooleanField(required=False)
    trigger = serializers.JSONField(required=False)
    conditions = serializers.JSONField(required=False)
    actions = serializers.JSONField(required=False)
    delay = serializers.JSONField(required=False, allow_null=True)
