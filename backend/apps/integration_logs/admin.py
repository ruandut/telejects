"""Django admin for platform staff: each company's log limit, and the entries themselves."""

from django import forms
from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from . import services
from .models import IntegrationLog, LogRetention


class LogRetentionForm(forms.ModelForm):
    class Meta:
        model = LogRetention
        fields = ["realm", "max_entries"]
        help_texts = {
            "max_entries": "How many provider requests this company keeps. Without a row here, "
            "INTEGRATION_LOGS_DEFAULT_LIMIT applies. Lowering it removes the oldest at once."
        }


@admin.register(LogRetention)
class LogRetentionAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    form = LogRetentionForm
    list_display = ["realm", "max_entries", "kept_now"]

    @admin.display(description="Kept now")
    def kept_now(self, obj):
        return IntegrationLog.objects.in_realm(obj.realm_id).count()

    def get_readonly_fields(self, request, obj=None):
        return ["realm"] if obj else []

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        services.prune(obj.realm_id)


@admin.register(IntegrationLog)
class IntegrationLogAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = [
        "created_at",
        "realm",
        "connection_name",
        "operation",
        "method",
        "status_code",
        "outcome",
    ]
    list_filter = ["operation", "outcome"]
    search_fields = ["url", "error", "connection_name"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
