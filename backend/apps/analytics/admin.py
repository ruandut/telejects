from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Dashboard, Widget


@admin.register(Dashboard)
class DashboardAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "project", "realm", "created_at"]
    readonly_fields = ["realm", "project", "created_by"]


@admin.register(Widget)
class WidgetAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["title", "kind", "dashboard"]
    readonly_fields = ["realm", "dashboard"]
