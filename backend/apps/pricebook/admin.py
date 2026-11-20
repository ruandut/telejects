"""Django admin for platform staff: Telejects' price book, its grants, and its files (0006)."""

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from apps.realms.admin import AcrossRealmsAdminMixin

from . import books
from .models import (
    AccessMedium,
    CatalogueProduct,
    ConnectProduct,
    PriceBook,
    PriceBookGrant,
    PriceDefinition,
)


class GrantInline(AcrossRealmsAdminMixin, admin.TabularInline):
    model = PriceBookGrant
    extra = 0
    fields = ["realm", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(PriceBook)
class PriceBookAdmin(admin.ModelAdmin):
    list_display = ["name", "available_to_all"]
    inlines = [GrantInline]


@admin.register(CatalogueProduct)
class CatalogueProductAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "provider", "product_code", "product_id"]
    list_filter = ["provider"]
    search_fields = ["name", "product_code"]


@admin.register(AccessMedium)
class AccessMediumAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "provider_access_medium_identifier_id"]
    search_fields = ["name"]


@admin.register(ConnectProduct)
class ConnectProductAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "book", "definition_count"]
    list_filter = ["book"]
    search_fields = ["name"]
    filter_horizontal = ["product_definitions"]

    @admin.display(description="Definitions")
    def definition_count(self, obj):
        return obj.product_definitions.count()


class CsvImportForm(forms.Form):
    csv_file = forms.FileField(label="Import items from")


@admin.register(PriceDefinition)
class PriceDefinitionAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "access_medium",
        "product",
        "provider",
        "monthly_recurring_cost",
        "none_recurring_cost",
        "duration",
        "data_allocation",
        "data_allocation_notes",
        "max_bandwidth",
        "max_upload_bandwidth",
        "medium",
    ]
    list_filter = ["provider", "sublayer", "medium"]
    search_fields = ["name", "product__name", "access_medium__name"]

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("import/", view(self.import_csv), name="pricebook_import_csv"),
            path("template/", view(self.template_csv), name="pricebook_template_csv"),
            path("export-csv/", view(self.export_csv), name="pricebook_export_csv"),
            path("export-pdf/", view(self.export_pdf), name="pricebook_export_pdf"),
            *super().get_urls(),
        ]

    def _allowed(self, request) -> bool:
        return self.has_change_permission(request)

    def import_csv(self, request):
        if not self._allowed(request):
            return HttpResponseRedirect("../")
        form = CsvImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            text = form.cleaned_data["csv_file"].read().decode("utf-8-sig")
            summary = books.import_csv(text)
            level = messages.WARNING if summary.failed else messages.SUCCESS
            self.message_user(request, str(summary), level=level)
            return HttpResponseRedirect("../")
        context = {**self.admin_site.each_context(request), "form": form, "opts": self.model._meta}
        return render(request, "admin/pricebook/pricedefinition/import.html", context)

    def _file(self, content, kind: str, name: str) -> HttpResponse:
        response = HttpResponse(content, content_type=kind)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    def template_csv(self, request):
        return self._file(books.template_csv(), "text/csv", "product-definitions.csv")

    def export_csv(self, request):
        day = timezone.localdate().strftime("%Y%m%d")
        return self._file(books.export_csv(), "text/csv", f"telejects_pricebook_{day}.csv")

    def export_pdf(self, request):
        day = timezone.localdate().strftime("%Y%m%d")
        return self._file(books.export_pdf(), "application/pdf", f"telejects_pricebook_{day}.pdf")
