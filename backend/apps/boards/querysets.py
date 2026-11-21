"""Query logic for boards. Every query starts `in_realm(...)` and then `visible_to(membership)`,
which keeps it inside the projects that person may open (projects.querysets)."""

from apps.projects.models import Project
from apps.projects.querysets import manages_all
from apps.realms.querysets import TenantQuerySet


def _visible_projects(membership):
    return Project.objects.in_realm(membership.realm_id).visible_to(membership).values("id")


class BoardQuerySet(TenantQuerySet):
    def visible_to(self, membership):
        if manages_all(membership):
            return self
        return self.filter(project_id__in=_visible_projects(membership))

    def of_project(self, project):
        return self.filter(project_id=project.pk)


class BoardChildQuerySet(TenantQuerySet):
    """Groups, columns and views: they belong to a board."""

    def visible_to(self, membership):
        if manages_all(membership):
            return self
        return self.filter(board__project_id__in=_visible_projects(membership))

    def of_board(self, board):
        return self.filter(board_id=board.pk)


class ItemQuerySet(BoardChildQuerySet):
    def live(self):
        return self.filter(archived_at__isnull=True)

    def archived(self):
        return self.filter(archived_at__isnull=False)


class ItemUpdateQuerySet(TenantQuerySet):
    def visible_to(self, membership):
        if manages_all(membership):
            return self
        return self.filter(item__board__project_id__in=_visible_projects(membership))

    def of_item(self, item):
        return self.filter(item_id=item.pk)


class ActivityQuerySet(ItemUpdateQuerySet):
    def of_board(self, board):
        return self.filter(board_id=board.pk)
