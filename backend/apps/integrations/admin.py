"""Django admin for platform staff: connector definitions, and every company's connections."""

import json

from django import forms
from django.contrib import admin
from pydantic import ValidationError

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Connection, ConnectorDefinition, ProviderProduct, SyncRun
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
    list_display = ["name", "realm", "connector_key", "enabled", "health", "health_checked_at"]
    list_filter = ["connector_key", "health", "enabled"]
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
