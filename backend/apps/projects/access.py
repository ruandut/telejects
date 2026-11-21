"""What a person may do in a project: view, edit or manage (0007).

The one place that decides it. Every app that hangs data off a project (boards, automations,
dashboards) asks here, and turns "can't see it" into a 404 and "can see it, can't do that" into a
403, so a hidden project looks exactly like a missing one.
"""

from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from .models import LEVEL_RANK, Level, Project, ProjectMember
from .querysets import manages_all, may_use_projects


def level_of(membership, project) -> str | None:
    if project is None or membership is None or project.realm_id != membership.realm_id:
        return None
    if manages_all(membership):
        return Level.MANAGE
    if not may_use_projects(membership):
        return None
    row = (
        ProjectMember.objects.in_realm(project.realm_id)
        .filter(project_id=project.pk, membership_id=membership.pk)
        .first()
    )
    return row.level if row else None


def allows(level: str | None, needed: str) -> bool:
    return level is not None and LEVEL_RANK[level] >= LEVEL_RANK[needed]


def can(membership, project, needed: str) -> bool:
    return allows(level_of(membership, project), needed)


def visible_project_ids(membership) -> list[int]:
    return list(
        Project.objects.in_realm(membership.realm_id)
        .visible_to(membership)
        .values_list("id", flat=True)
    )


def levels_by_project(membership) -> dict[int, str]:
    """Every project this person may open, with their level."""
    projects = Project.objects.in_realm(membership.realm_id).visible_to(membership)
    return dict(projects.with_level(membership).values_list("id", "my_level"))


def project_for(membership, project_id, needed: str = Level.VIEW) -> Project:
    """The project, if this person may open it (404 otherwise) and has `needed` (403
    otherwise)."""
    project = Project.objects.in_realm(membership.realm_id).visible_to(membership).by_id(project_id)
    if project is None:
        raise Http404
    require(membership, project, needed)
    return project


def require(membership, project, needed: str) -> str:
    level = level_of(membership, project)
    if level is None:
        raise Http404
    if not allows(level, needed):
        raise PermissionDenied(
            "You can only view this project."
            if level == Level.VIEW
            else "You need manage access to this project to do that."
        )
    return level
