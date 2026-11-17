from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Invitation


@admin.register(Invitation)
class InvitationAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["membership", "realm", "created_at", "expires_at", "used_at"]
    list_select_related = ["membership__user", "realm"]
    readonly_fields = ["token_hash", "membership", "realm", "created_at", "used_at"]
