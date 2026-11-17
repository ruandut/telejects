"""Django admin for platform staff. Admin works across companies by nature, so its querysets
call `across_realms()` here, in one place (allowlisted in test_isolation.py)."""

from django.contrib import admin

from .models import Realm, RealmMembership, Role, TenantModel
from .querysets import TenantQuerySet


def _across(queryset):
    return queryset.across_realms() if isinstance(queryset, TenantQuerySet) else queryset


class AcrossRealmsAdminMixin:
    """For admin classes over company-owned rows: lists and choices span every company."""

    def get_queryset(self, request):
        return _across(super().get_queryset(request))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if issubclass(db_field.related_model, TenantModel) and "queryset" not in kwargs:
            kwargs["queryset"] = _across(db_field.related_model._default_manager.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class RoleInline(AcrossRealmsAdminMixin, admin.TabularInline):
    model = Role
    extra = 0
    fields = ["key", "name", "is_system", "position"]
    readonly_fields = ["key", "is_system"]


class MembershipInline(AcrossRealmsAdminMixin, admin.TabularInline):
    model = RealmMembership
    extra = 0
    fields = ["user", "name", "role", "status"]
    autocomplete_fields = ["user"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Only the company's own roles: the database refuses any other anyway.
        realm_id = request.resolver_match.kwargs.get("object_id")
        if db_field.name == "role" and realm_id:
            kwargs["queryset"] = Role.objects.in_realm(realm_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Realm)
class RealmAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
    inlines = [RoleInline, MembershipInline]
