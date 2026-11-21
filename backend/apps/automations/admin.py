from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Automation, AutomationRun


@admin.register(Automation)
class AutomationAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "board", "enabled", "run_count", "last_run_at"]
    readonly_fields = ["realm", "board", "created_by"]


@admin.register(AutomationRun)
class AutomationRunAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["automation", "item_name", "status", "message", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["realm", "automation", "item", "by"]
