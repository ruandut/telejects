"""Insights (0007): dashboards, widgets and their data, and the portfolio.

A project's dashboards are seen by anyone who can open the project and changed with manage level
on it; company dashboards are seen by anyone in Projects and changed with `projects.manage`.
Every number is worked out for the person asking, over only the items they may see.
"""

from django.http import Http404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.boards.context import BoardContext
from apps.boards.models import Group
from apps.projects import access
from apps.projects.models import Level
from apps.projects.querysets import manages_all
from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import query, services
from .models import Dashboard, Widget

PERMISSIONS = [InRealm, HasRealmPermission("projects.view", write="projects.view")]


class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ["id", "dashboard", "title", "kind", "config", "position", "width"]
        read_only_fields = fields


class DashboardSerializer(serializers.ModelSerializer):
    widgets = WidgetSerializer(many=True, read_only=True)

    class Meta:
        model = Dashboard
        fields = ["id", "project", "name", "position", "widgets", "created_at"]
        read_only_fields = fields


def _require_change(request, project):
    """A project's dashboards change with manage level on it; the company's with
    `projects.manage`."""
    if project is None:
        if not manages_all(request.membership):
            raise PermissionDenied("You need permission to manage projects.")
        return
    access.require(request.membership, project, Level.MANAGE)


def _scope(request, project, boards=()) -> query.Scope:
    return query.Scope(request.realm.id, request.membership, project, boards)


class DashboardViewSet(RealmScopedMixin, viewsets.GenericViewSet):
    permission_classes = PERMISSIONS
    queryset = Dashboard.objects.select_related("project")
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.membership)

    def list(self, request):
        rows = self.get_queryset()
        project_id = request.query_params.get("project")
        if project_id:
            rows = rows.of_project(access.project_for(request.membership, project_id))
        else:
            rows = rows.company()
        return Response(DashboardSerializer(rows.prefetch_related("widgets"), many=True).data)

    def create(self, request):
        project_id = request.data.get("project")
        project = access.project_for(request.membership, project_id) if project_id else None
        _require_change(request, project)
        dashboard = services.create_dashboard(
            request.realm,
            project,
            request.data.get("name"),
            request.user,
            starter=bool(request.data.get("starter")),
        )
        return Response(DashboardSerializer(dashboard).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(DashboardSerializer(self.get_object()).data)

    def partial_update(self, request, pk=None):
        dashboard = self.get_object()
        _require_change(request, dashboard.project)
        fields = {k: request.data[k] for k in ("name", "position") if k in request.data}
        return Response(DashboardSerializer(services.update_dashboard(dashboard, **fields)).data)

    def destroy(self, request, pk=None):
        dashboard = self.get_object()
        _require_change(request, dashboard.project)
        services.delete_dashboard(dashboard)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WidgetViewSet(RealmScopedMixin, viewsets.GenericViewSet):
    permission_classes = PERMISSIONS
    queryset = Widget.objects.select_related("dashboard__project")
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.membership)

    def create(self, request):
        dashboard = (
            Dashboard.objects.in_realm(request.realm)
            .visible_to(request.membership)
            .by_id(request.data.get("dashboard"))
        )
        if dashboard is None:
            raise Http404
        _require_change(request, dashboard.project)
        widget = services.create_widget(
            dashboard,
            request.data.get("title"),
            request.data.get("kind"),
            self._boards_checked(request, dashboard, request.data.get("config")),
            request.data.get("width", 1),
        )
        return Response(WidgetSerializer(widget).data, status=status.HTTP_201_CREATED)

    def _boards_checked(self, request, dashboard, config):
        """A widget may only name boards inside its dashboard's scope that the person sees."""
        config = config if isinstance(config, dict) else {}
        wanted = query.clean(config)["boards"]
        if wanted:
            allowed = {b.pk for b in _scope(request, dashboard.project).boards}
            if set(wanted) - allowed:
                raise serializers.ValidationError({"config": "Choose boards from this dashboard."})
        return config

    def partial_update(self, request, pk=None):
        widget = self.get_object()
        _require_change(request, widget.dashboard.project)
        fields = {
            k: request.data[k]
            for k in ("title", "kind", "config", "width", "position")
            if k in request.data
        }
        if "config" in fields:
            fields["config"] = self._boards_checked(request, widget.dashboard, fields["config"])
        return Response(WidgetSerializer(services.update_widget(widget, **fields)).data)

    def destroy(self, request, pk=None):
        widget = self.get_object()
        _require_change(request, widget.dashboard.project)
        services.delete_widget(widget)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def data(self, request, pk=None):
        widget = self.get_object()
        config = query.clean(widget.config)
        return Response(
            query.run(config, _scope(request, widget.dashboard.project, config["boards"]))
        )


class InsightsViewSet(viewsets.ViewSet):
    permission_classes = PERMISSIONS

    @action(detail=False, methods=["post"])
    def preview(self, request):
        """A widget's data before it is saved: {project?, config}."""
        project_id = request.data.get("project")
        project = access.project_for(request.membership, project_id) if project_id else None
        config = query.clean(request.data.get("config"))
        return Response(query.run(config, _scope(request, project, config["boards"])))

    @action(detail=False, methods=["get"])
    def portfolio(self, request):
        return Response(query.portfolio(request.realm.id, request.membership))

    @action(detail=False, methods=["get"])
    def sources(self, request):
        """What a widget can be built from: the boards in scope, their columns and groups."""
        project_id = request.query_params.get("project")
        project = access.project_for(request.membership, project_id) if project_id else None
        boards = _scope(request, project).boards
        groups = {}
        for g in Group.objects.in_realm(request.realm).filter(board_id__in=[b.pk for b in boards]):
            groups.setdefault(g.board_id, []).append({"id": g.pk, "name": g.name})
        out = []
        for board in boards:
            ctx = BoardContext(board, request.membership)
            out.append(
                {
                    "id": board.pk,
                    "name": board.name,
                    "project": {"id": board.project_id, "name": board.project.name},
                    "groups": groups.get(board.pk, []),
                    "columns": [
                        {
                            "key": c.key,
                            "title": c.title,
                            "type": c.type,
                            "labels": [
                                label["label"]
                                for label in c.settings.get("labels", c.settings.get("options", []))
                            ],
                        }
                        for c in ctx.columns
                    ],
                }
            )
        return Response(out)
