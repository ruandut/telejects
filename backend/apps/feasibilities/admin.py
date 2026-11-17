from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import FeasibilityRun, ProviderCheck


@admin.register(FeasibilityRun)
class FeasibilityRunAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = [
        "name",
        "realm",
        "status",
        "site_count",
        "checks_total",
        "checks_failed",
        "created_at",
    ]
    list_filter = ["status"]
    readonly_fields = ["realm", "created_by", "products", "columns", "mapping"]


@admin.register(ProviderCheck)
class ProviderCheckAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["id", "run", "connection", "status", "attempts", "error_kind", "duration_ms"]
    list_filter = ["status", "error_kind"]
    readonly_fields = ["realm", "run", "connection", "sites"]
