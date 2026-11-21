from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["title", "recipient", "kind", "created_at", "read_at"]
    readonly_fields = ["realm", "recipient"]
