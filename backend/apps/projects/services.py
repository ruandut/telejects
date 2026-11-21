"""Creating and changing projects, and sharing them (0007). The only place that writes them."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.realms.models import RealmMembership

from .models import Level, Project, ProjectMember
from .signals import project_created

EDITABLE = ("name", "client", "description", "status", "colour", "start_date", "end_date", "owner")


def _check_dates(start, end):
    if start and end and end < start:
        raise ValidationError({"end_date": "The end can't be before the start."})


@transaction.atomic
def create_project(realm, by: RealmMembership, *, template: str = "blank", **fields) -> Project:
    _check_dates(fields.get("start_date"), fields.get("end_date"))
    fields.setdefault("owner", by)
    project = Project.objects.create(realm=realm, created_by=by.user, **fields)
    if fields["owner"] is not None:
        ProjectMember.objects.create(
            realm=realm, project=project, membership=fields["owner"], level=Level.MANAGE
        )
    project_created.send(sender=Project, project=project, template=template, by=by)
    return project


@transaction.atomic
def update_project(project: Project, **fields) -> Project:
    unknown = set(fields) - set(EDITABLE)
    if unknown:
        raise ValueError(f"Can't change {sorted(unknown)}")
    _check_dates(
        fields.get("start_date", project.start_date), fields.get("end_date", project.end_date)
    )
    for name, value in fields.items():
        setattr(project, name, value)
    project.save()
    owner = fields.get("owner")
    if owner is not None:
        share(project, owner, Level.MANAGE)
    return project


def delete_project(project: Project) -> None:
    project.delete()


def _person(project: Project, membership) -> RealmMembership:
    if membership is None or membership.realm_id != project.realm_id:
        raise ValidationError({"membership": "Choose someone in this company."})
    if membership.status == RealmMembership.Status.REMOVED:
        raise ValidationError({"membership": "They no longer work in this company."})
    return membership


@transaction.atomic
def share(project: Project, membership, level: str) -> ProjectMember:
    """Give someone this level on the project (or change theirs)."""
    if level not in Level.values:
        raise ValidationError({"level": "Choose view, edit or manage."})
    membership = _person(project, membership)
    row, _ = ProjectMember.objects.in_realm(project.realm_id).update_or_create(
        realm_id=project.realm_id,
        project=project,
        membership=membership,
        defaults={"level": level},
    )
    return row


@transaction.atomic
def unshare(project: Project, membership) -> None:
    ProjectMember.objects.in_realm(project.realm_id).of_project(project).filter(
        membership_id=membership.pk
    ).delete()
    if project.owner_id == membership.pk:
        project.owner = None
        project.save(update_fields=["owner", "updated_at"])
