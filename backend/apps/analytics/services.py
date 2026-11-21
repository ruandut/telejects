"""Dashboards and widgets: the only place that writes them (0007)."""

from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import ValidationError

from apps.boards.context import BoardContext
from apps.boards.models import Board

from . import query
from .models import Dashboard, Widget


def _name(value, what="dashboard") -> str:
    value = str(value or "").strip()[:120]
    if not value:
        raise ValidationError({"name": f"Give the {what} a name."})
    return value


@transaction.atomic
def create_dashboard(realm, project, name, user, starter=False) -> Dashboard:
    rows = Dashboard.objects.in_realm(realm)
    rows = rows.of_project(project) if project else rows.company()
    top = rows.aggregate(top=Max("position"))["top"] or 0
    dashboard = Dashboard.objects.create(
        realm=realm, project=project, name=_name(name), created_by=user, position=top + 1
    )
    if starter:
        for i, (title, kind, config, width) in enumerate(_starter(realm, project)):
            Widget.objects.create(
                realm=realm,
                dashboard=dashboard,
                title=title,
                kind=kind,
                config=query.clean(config),
                position=i,
                width=width,
            )
    return dashboard


def _starter(realm, project):
    """Widgets a new dashboard starts with, named after the first board's own columns."""
    boards = Board.objects.in_realm(realm)
    board = boards.of_project(project).first() if project else boards.first()
    status, money, due = "Status", None, None
    if board is not None:
        ctx = BoardContext(board)
        if ctx.status_column is not None:
            status = ctx.status_column.title
        money = next((c.title for c in ctx.columns if c.type in ("number", "formula")), None)
        due = ctx.due_column.title if ctx.due_column is not None else None
    widgets = [
        ("Items", "number", {"metric": {"op": "count"}}, 1),
        ("Done or not", "pie", {"metric": {"op": "count"}, "group_by": {"by": "done"}}, 1),
        (f"By {status.lower()}", "pie", {"group_by": {"by": "column", "column": status}}, 1),
    ]
    if project is None:
        widgets.append(
            (
                f"{status} by project",
                "stacked",
                {
                    "group_by": {"by": "project"},
                    "series_by": {"by": "column", "column": status},
                },
                3,
            )
        )
    else:
        widgets.append(
            (
                f"{status} by group",
                "stacked",
                {"group_by": {"by": "group"}, "series_by": {"by": "column", "column": status}},
                2,
            )
        )
    widgets.append(
        (
            "Created per week",
            "area",
            {"group_by": {"by": "created"}, "bucket": "week"},
            2 if project else 3,
        )
    )
    if due:
        widgets.append(
            (
                f"{due} per month",
                "bar",
                {"group_by": {"by": "column", "column": due}, "bucket": "month"},
                2,
            )
        )
    if money:
        widgets.append(
            (
                f"{money} by {status.lower()}",
                "bar",
                {
                    "metric": {"op": "sum", "column": money},
                    "group_by": {"by": "column", "column": status},
                },
                1 if due else 2,
            )
        )
    widgets.append(
        ("Completed per week", "line", {"group_by": {"by": "completed"}, "bucket": "week"}, 3)
    )
    return widgets


@transaction.atomic
def update_dashboard(dashboard, **fields) -> Dashboard:
    if "name" in fields:
        dashboard.name = _name(fields["name"])
    if "position" in fields:
        dashboard.position = fields["position"]
    dashboard.save()
    return dashboard


def delete_dashboard(dashboard) -> None:
    dashboard.delete()


def _kind(value):
    if value not in Widget.Kind.values:
        raise ValidationError({"kind": "Choose a chart type."})
    return value


def _width(value):
    try:
        return max(1, min(int(value), 3))
    except TypeError, ValueError:
        return 1


@transaction.atomic
def create_widget(dashboard, title, kind, config, width=1) -> Widget:
    rows = Widget.objects.in_realm(dashboard.realm_id).filter(dashboard=dashboard)
    if rows.count() >= 40:
        raise ValidationError({"detail": "A dashboard holds at most 40 widgets."})
    return Widget.objects.create(
        realm_id=dashboard.realm_id,
        dashboard=dashboard,
        title=_name(title, "widget"),
        kind=_kind(kind),
        config=query.clean(config),
        width=_width(width),
        position=(rows.aggregate(top=Max("position"))["top"] or 0) + 1,
    )


@transaction.atomic
def update_widget(widget, **fields) -> Widget:
    if "title" in fields:
        widget.title = _name(fields["title"], "widget")
    if "kind" in fields:
        widget.kind = _kind(fields["kind"])
    if "config" in fields:
        widget.config = query.clean(fields["config"])
    if "width" in fields:
        widget.width = _width(fields["width"])
    if "position" in fields:
        widget.position = float(fields["position"])
    widget.save()
    return widget


def delete_widget(widget) -> None:
    widget.delete()
