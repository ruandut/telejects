"""Query logic for projects. A project is always reached through `visible_to(membership)` after
`in_realm`: belonging to the company is not enough to see a project (0007)."""

from django.db.models import CharField, OuterRef, Subquery, Value

from apps.realms.querysets import TenantQuerySet


def manages_all(membership) -> bool:
    """Whether this person opens and changes every project of the company."""
    return bool(
        membership is not None and membership.is_active and membership.has_perm("projects.manage")
    )


def may_use_projects(membership) -> bool:
    return bool(
        membership is not None and membership.is_active and membership.has_perm("projects.view")
    )


class ProjectQuerySet(TenantQuerySet):
    def visible_to(self, membership):
        """The projects this person may open: every one for a manager, otherwise those shared
        with them. Nothing for someone without Projects at all."""
        if manages_all(membership):
            return self
        if not may_use_projects(membership):
            return self.none()
        return self.filter(members__membership_id=membership.pk)

    def with_level(self, membership):
        """Annotates `my_level`: what this person may do in each project."""
        if manages_all(membership):
            return self.annotate(my_level=Value("manage", output_field=CharField()))
        from .models import ProjectMember  # models.py imports this module

        level = ProjectMember.objects.in_realm(membership.realm_id).filter(
            project_id=OuterRef("pk"), membership_id=membership.pk
        )
        return self.annotate(my_level=Subquery(level.values("level")[:1]))

    def current(self):
        return self.exclude(status="archived")

    def search(self, text: str):
        from django.db.models import Q

        text = (text or "").strip()[:100]
        if not text:
            return self
        return self.filter(Q(name__icontains=text) | Q(client__icontains=text))


class ProjectMemberQuerySet(TenantQuerySet):
    def of_project(self, project):
        return self.filter(project_id=project.pk)

    def of_membership(self, membership):
        return self.filter(membership_id=membership.pk)
