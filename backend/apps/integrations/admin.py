"""Django admin for platform staff: connector definitions, and every company's connections."""

import json

from django import forms
from django.conf import settings as django_settings
from django.contrib import admin
from pydantic import ValidationError

from apps.realms.admin import AcrossRealmsAdminMixin

from . import services
from .models import (
    Connection,
    ConnectorDefinition,
    PlatformAccount,
    PlatformGrant,
    ProviderProduct,
    SyncRun,
)
from .spec import ConnectorSpec


class DefinitionForm(forms.ModelForm):
    class Meta:
        model = ConnectorDefinition
        fields = ["key", "version", "spec", "published"]

    def clean_spec(self):
        spec = self.cleaned_data["spec"]
        try:
            parsed = ConnectorSpec.model_validate(spec)
        except ValidationError as error:
            raise forms.ValidationError(str(error)) from None
        return json.loads(parsed.model_dump_json(exclude_defaults=True))

    def clean(self):
        cleaned = super().clean()
        spec = cleaned.get("spec")
        if spec and cleaned.get("key") and spec.get("key") != cleaned["key"]:
            raise forms.ValidationError("The key must match the definition's key.")
        return cleaned


@admin.register(ConnectorDefinition)
class ConnectorDefinitionAdmin(admin.ModelAdmin):
    """A saved version never changes: edit by adding a new version."""

    form = DefinitionForm
    list_display = ["key", "version", "published", "created_at", "created_by"]
    list_filter = ["key", "published"]

    def get_readonly_fields(self, request, obj=None):
        return ["key", "version", "spec", "created_by"] if obj else ["created_by"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Connection)
class ConnectionAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "realm", "connector_key", "credentials", "enabled", "health"]
    list_filter = ["connector_key", "credentials", "health", "enabled"]
    exclude = ["secrets_encrypted"]
    readonly_fields = ["realm", "connector_key", "health", "health_error", "health_checked_at"]


@admin.register(ProviderProduct)
class ProviderProductAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "code", "product_type", "connection", "realm", "retired_at"]
    list_filter = ["product_type"]
    readonly_fields = ["realm", "connection", "code", "raw", "first_seen_at"]


@admin.register(SyncRun)
class SyncRunAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["connection", "realm", "kind", "trigger", "outcome", "started_at"]
    list_filter = ["kind", "outcome"]


# --- Telejects' own provider accounts (0004) ---------------------------------------------------


def _env_keys():
    return [(key, key) for key in sorted(django_settings.INTEGRATIONS_PLATFORM_ACCOUNTS)]


class PlatformAccountForm(forms.ModelForm):
    """Telejects' accounts are configured in .env (INTEGRATIONS_PLATFORM_ACCOUNTS); here staff
    only name them, switch them on or off, and choose whether every company gets them."""

    class Meta:
        model = PlatformAccount
        fields = ["name", "connector_key", "env_key", "enabled", "available_to_all"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["env_key"] = forms.ChoiceField(
            choices=_env_keys(), help_text=self.fields["env_key"].help_text
        )

    def clean(self):
        cleaned = super().clean()
        key = cleaned.get("connector_key")
        if key and ConnectorDefinition.objects.latest_for(key) is None:
            raise forms.ValidationError("There's no published connector with that key.")
        return cleaned


@admin.register(PlatformAccount)
class PlatformAccountAdmin(admin.ModelAdmin):
    form = PlatformAccountForm
    list_display = ["name", "connector_key", "enabled", "available_to_all", "configured", "health"]
    list_filter = ["connector_key", "health", "enabled", "available_to_all"]
    readonly_fields = ["in_env", "health", "health_error", "health_checked_at"]
    actions = ["check_now"]

    @admin.display(description="In .env")
    def in_env(self, obj):
        """Which of its fields .env sets, never the values."""
        entry = django_settings.INTEGRATIONS_PLATFORM_ACCOUNTS.get(obj.env_key, {})
        parts = [
            f"{k}: {'set' if v else 'missing'}"
            for group in ("secrets", "settings")
            for k, v in sorted(entry.get(group, {}).items())
        ]
        return ", ".join(parts) or "Nothing (no such entry)"

    @admin.display(boolean=True)
    def configured(self, obj):
        return obj.configured

    @admin.action(description="Check the credentials now")
    def check_now(self, request, queryset):
        for account in queryset:
            ok = services.test_platform_account(account.id)
            self.message_user(request, f"{account}: {'accepted' if ok else 'failing'}")


@admin.register(PlatformGrant)
class PlatformGrantAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    """Granting connects the company through the account; deleting withdraws it."""

    list_display = ["account", "realm", "created_at"]
    list_filter = ["account"]
    fields = ["realm", "account"]

    def get_readonly_fields(self, request, obj=None):
        return ["realm", "account"] if obj else []

    def save_model(self, request, obj, form, change):
        if not change:
            grant = services.grant_platform_account(obj.realm, obj.account)
            obj.pk = grant.pk

    def delete_model(self, request, obj):
        services.withdraw_platform_account(obj.realm, obj.account)

    def delete_queryset(self, request, queryset):
        for grant in queryset.select_related("realm", "account"):
            services.withdraw_platform_account(grant.realm, grant.account)
