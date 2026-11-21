from django.db.models import Q

from apps.projects.models import Project
from apps.projects.querysets import manages_all, may_use_projects
from apps.realms.querysets import TenantQuerySet


class DashboardQuerySet(TenantQuerySet):
    def visible_to(self, membership):
        """Company dashboards for anyone in Projects; a project's for those who can open it."""
        if manages_all(membership):
            return self
        if not may_use_projects(membership):
            return self.none()
        projects = Project.objects.in_realm(membership.realm_id).visible_to(membership)
        return self.filter(Q(project__isnull=True) | Q(project_id__in=projects.values("id")))

    def company(self):
        return self.filter(project__isnull=True)

    def of_project(self, project):
        return self.filter(project_id=project.pk)


class WidgetQuerySet(TenantQuerySet):
    def visible_to(self, membership):
        from .models import Dashboard

        dashboards = Dashboard.objects.in_realm(membership.realm_id).visible_to(membership)
        return self.filter(dashboard_id__in=dashboards.values("id"))
