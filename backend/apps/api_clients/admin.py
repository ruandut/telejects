from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import ApiClient


@admin.register(ApiClient)
class ApiClientAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    """Read-only for staff: companies make and revoke their own clients in the portal."""

    list_display = ["name", "realm", "client_id", "created_by", "last_used_at", "revoked_at"]
    list_filter = ["realm"]
    search_fields = ["name", "client_id"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
