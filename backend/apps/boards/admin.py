from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Board, Column, Group, Item


@admin.register(Board)
class BoardAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "project", "realm", "created_at"]
    readonly_fields = ["realm", "project"]


@admin.register(Column)
class ColumnAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["title", "type", "key", "board"]
    readonly_fields = ["realm", "board", "key", "type"]


@admin.register(Group)
class GroupAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "board"]
    readonly_fields = ["realm", "board"]


@admin.register(Item)
class ItemAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "number", "board", "done", "created_at"]
    readonly_fields = ["realm", "board", "group", "created_by"]
