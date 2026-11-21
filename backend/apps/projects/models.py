"""Projects: the work a company does for a client, and who may work on each one (0007).

A project is reached only through `Project.objects.in_realm(realm).visible_to(membership)`.
People with `projects.manage` see and change every project; everyone else sees the projects
shared with them through a ProjectMember, at its level. Boards, automations and dashboards hang
off a project and inherit its access (access.py).
"""

from django.conf import settings
from django.db import models

from apps.realms.models import RealmMembership, TenantModel

from .querysets import ProjectMemberQuerySet, ProjectQuerySet


class Level(models.TextChoices):
    VIEW = "view", "View"  # read boards, dashboards and updates
    EDIT = "edit", "Edit"  # also change items and write updates
    MANAGE = "manage", "Manage"  # also columns, groups, views, automations, dashboards, access


LEVEL_RANK = {Level.VIEW: 1, Level.EDIT: 2, Level.MANAGE: 3}


class Project(TenantModel):
    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        DONE = "done", "Done"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=120)
    client = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True, max_length=4000)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    colour = models.CharField(max_length=20, default="blue")
    owner = models.ForeignKey(
        RealmMembership, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "name"], name="project_name_unique_in_realm"),
            models.UniqueConstraint(fields=["realm", "id"], name="project_realm_id_pair"),
        ]

    def __str__(self):
        return self.name


class ProjectMember(TenantModel):
    """Someone the project is shared with, and what they may do in it."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    membership = models.ForeignKey(RealmMembership, on_delete=models.CASCADE, related_name="+")
    level = models.CharField(max_length=6, choices=Level.choices, default=Level.VIEW)
    added_at = models.DateTimeField(auto_now_add=True)

    objects = ProjectMemberQuerySet.as_manager()

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "membership"], name="one_project_member_per_person"
            )
        ]

    def __str__(self):
        return f"{self.membership_id} on {self.project_id} ({self.level})"
