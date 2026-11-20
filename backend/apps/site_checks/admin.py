from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import SiteCheck, SiteCheckCall, SiteCheckResult


class CallInline(AcrossRealmsAdminMixin, admin.TabularInline):
    model = SiteCheckCall
    extra = 0
    fields = ["connector_key", "status", "credentials", "error", "duration_ms"]
    readonly_fields = fields
    can_delete = False


class ResultInline(AcrossRealmsAdminMixin, admin.TabularInline):
    model = SiteCheckResult
    extra = 0
    fields = ["connector_key", "product_code", "variant_name", "status", "bandwidths"]
    readonly_fields = fields
    can_delete = False


@admin.register(SiteCheck)
class SiteCheckAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["id", "realm", "latitude", "longitude", "created_at"]
    list_filter = ["realm"]
    inlines = [CallInline, ResultInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
