from django.contrib import admin

from apps.realms.admin import AcrossRealmsAdminMixin

from .models import Project, ProjectMember


@admin.register(Project)
class ProjectAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["name", "client", "realm", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["realm", "created_by", "owner"]


@admin.register(ProjectMember)
class ProjectMemberAdmin(AcrossRealmsAdminMixin, admin.ModelAdmin):
    list_display = ["project", "membership", "level", "added_at"]
    readonly_fields = ["realm", "project", "membership"]
