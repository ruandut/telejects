"""Boards, groups, columns, views, items and updates (0007).

Every lookup starts `in_realm(request.realm).visible_to(request.membership)`, so a board in a
project the person can't open is a 404, exactly like another company's. Then the project level
decides: view to read, edit to change items and write updates, manage to change the board's
structure (columns, groups, views) and the board itself.
"""

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.feasibilities.models import FeasibilityRun
from apps.projects import access
from apps.projects.models import Level
from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import file_import, services, sources
from .context import BoardContext
from .models import Board, BoardView, Column, Group, Item, ItemActivity, ItemUpdate
from .serializers import (
    ActivitySerializer,
    BoardChangeSerializer,
    BoardListSerializer,
    ColumnInputSerializer,
    ColumnSerializer,
    GroupInputSerializer,
    GroupSerializer,
    ItemChangeSerializer,
    ItemUpdateSerializer,
    NewBoardSerializer,
    NewItemSerializer,
    UpdateInputSerializer,
    ViewInputSerializer,
    ViewSerializer,
    board_data,
    item_rows,
    items_of,
)
from .templates import catalogue

PERMISSIONS = [InRealm, HasRealmPermission("projects.view", write="projects.view")]


def _valid(serializer_class, data, partial=False):
    serializer = serializer_class(data=data, partial=partial)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _actor(request) -> services.Actor:
    return services.Actor(membership=request.membership)


def board_for(request, board_id, needed=Level.VIEW) -> tuple[Board, str]:
    board = (
        Board.objects.in_realm(request.realm)
        .visible_to(request.membership)
        .select_related("project")
        .by_id(board_id)
    )
    if board is None:
        raise Http404
    return board, access.require(request.membership, board.project, needed)


class BoardScoped(RealmScopedMixin, viewsets.GenericViewSet):
    permission_classes = PERMISSIONS
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.membership)

    def _object(self, needed=Level.VIEW):
        row = self.get_object()
        board = row if isinstance(row, Board) else row.board
        level = access.require(self.request.membership, board.project, needed)
        return row, level


class BoardViewSet(BoardScoped):
    queryset = Board.objects.select_related("project", "feasibility_run")

    def list(self, request):
        project = access.project_for(request.membership, request.query_params.get("project"))
        from django.db.models import Count, Q

        boards = (
            Board.objects.in_realm(request.realm)
            .of_project(project)
            .annotate(
                item_count=Count("items", filter=Q(items__archived_at__isnull=True)),
                done_count=Count(
                    "items", filter=Q(items__archived_at__isnull=True, items__done=True)
                ),
            )
            .order_by("position", "id")
        )
        return Response(BoardListSerializer(boards, many=True).data)

    def create(self, request):
        data = _valid(NewBoardSerializer, request.data)
        project = access.project_for(request.membership, data["project"], Level.MANAGE)
        if data.get("feasibility_run"):
            # Its sites become the items: needs seeing the company's feasibility runs too.
            if not request.membership.has_perm("feasibilities.view"):
                raise PermissionDenied("You need permission to see feasibility runs.")
            run = (
                FeasibilityRun.objects.in_realm(request.realm)
                .listed()
                .by_id(data["feasibility_run"])
            )
            if run is None:
                raise ValidationError({"feasibility_run": "Choose one of this company's runs."})
            board = sources.board_from_run(project, run, data.get("name", ""), _actor(request))
        else:
            board = services.create_board(
                project, data.get("name", ""), data.get("template", "blank"), _actor(request)
            )
        return Response(board_data(board, Level.MANAGE), status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        board, level = self._object()
        return Response(board_data(board, level))

    def partial_update(self, request, pk=None):
        board, level = self._object(Level.MANAGE)
        services.update_board(board, **_valid(BoardChangeSerializer, request.data, partial=True))
        return Response(board_data(board, level))

    def destroy(self, request, pk=None):
        board, _ = self._object(Level.MANAGE)
        services.delete_board(board)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="from-file")
    def from_file(self, request):
        """A new board from a spreadsheet's rows (a monday.com export or a CSV):
        {project, name?, rows: [[cell, ...], ...]}. Needs manage on the project."""
        project = access.project_for(request.membership, request.data.get("project"), Level.MANAGE)
        name = str(request.data.get("name") or "").strip()[:120]
        board, result = file_import.board_from_file(
            project, request.data.get("rows"), name, _actor(request)
        )
        board = Board.objects.in_realm(request.realm).select_related("project").get(pk=board.pk)
        return Response({**board_data(board, Level.MANAGE), "import": result}, status=201)

    @action(detail=False, methods=["get"])
    def templates(self, request):
        return Response(catalogue())

    @action(detail=True, methods=["get", "post"])
    def items(self, request, pk=None):
        """GET: the board's items (?archived=1 for archived ones, ?ids= for some). POST: add
        one (edit level)."""
        if request.method == "POST":
            board, _ = self._object(Level.EDIT)
            data = _valid(NewItemSerializer, request.data)
            item = services.create_item(
                board,
                data["name"],
                group=data.get("group"),
                values=data.get("values") or {},
                actor=_actor(request),
                top=data.get("top", False),
            )
            ctx = BoardContext(board, request.membership)
            return Response(item_rows(ctx, items_of(ctx, [item.pk]))[0], status=201)
        board, _ = self._object()
        ctx = BoardContext(board, request.membership)
        ids = request.query_params.get("ids")
        wanted = [int(i) for i in ids.split(",") if i.isdigit()][:500] if ids else None
        archived = request.query_params.get("archived") == "1"
        return Response(item_rows(ctx, items_of(ctx, wanted, archived)))

    @action(detail=True, methods=["post"], url_path="import")
    def import_rows(self, request, pk=None):
        board, _ = self._object(Level.EDIT)
        return Response(services.import_rows(board, request.data.get("rows"), _actor(request)))

    @action(detail=True, methods=["post"])
    def batch(self, request, pk=None):
        """{"items": [...], "action": archive|restore|delete|move|set|duplicate, ...}"""
        board, _ = self._object(Level.EDIT)
        ids = [int(i) for i in request.data.get("items") or [] if str(i).isdigit()]
        done = services.batch(
            board, ids, str(request.data.get("action")), _actor(request), request.data
        )
        return Response({"done": done})

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        board, _ = self._object()
        rows = (
            ItemActivity.objects.in_realm(request.realm)
            .of_board(board)
            .select_related("actor__user", "item")[:100]
        )
        return Response(ActivitySerializer(rows, many=True).data)


class GroupViewSet(BoardScoped):
    queryset = Group.objects.select_related("board__project")

    def create(self, request):
        data = _valid(GroupInputSerializer, request.data)
        board, _ = board_for(request, data.get("board"), Level.MANAGE)
        group = services.create_group(
            board, data.get("name", ""), data.get("colour", "blue"), data.get("top", False)
        )
        return Response(GroupSerializer(group).data, status=201)

    def partial_update(self, request, pk=None):
        group, _ = self._object(Level.MANAGE)
        data = _valid(GroupInputSerializer, request.data, partial=True)
        data.pop("board", None)
        data.pop("top", None)
        return Response(GroupSerializer(services.update_group(group, **data)).data)

    def destroy(self, request, pk=None):
        group, _ = self._object(Level.MANAGE)
        services.delete_group(group)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ColumnViewSet(BoardScoped):
    queryset = Column.objects.select_related("board__project")

    def create(self, request):
        data = _valid(ColumnInputSerializer, request.data)
        board, _ = board_for(request, data.get("board"), Level.MANAGE)
        if data.get("settings", {}).get("board"):
            # A connect column may only link a board this person can open.
            board_for(request, data["settings"]["board"])
        column = services.create_column(
            board,
            data.get("title", ""),
            data.get("type", ""),
            data.get("settings"),
            data.get("description", ""),
            data.get("after"),
        )
        return Response(ColumnSerializer(column).data, status=201)

    def partial_update(self, request, pk=None):
        column, _ = self._object(Level.MANAGE)
        data = _valid(ColumnInputSerializer, request.data, partial=True)
        for name in ("board", "type", "after"):
            data.pop(name, None)
        if column.type == "connect" and (data.get("settings") or {}).get("board"):
            board_for(request, data["settings"]["board"])
        return Response(ColumnSerializer(services.update_column(column, **data)).data)

    def destroy(self, request, pk=None):
        column, _ = self._object(Level.MANAGE)
        services.delete_column(column)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ViewViewSet(BoardScoped):
    queryset = BoardView.objects.select_related("board__project")

    def create(self, request):
        data = _valid(ViewInputSerializer, request.data)
        board, _ = board_for(request, data.get("board"), Level.MANAGE)
        view = services.create_view(
            board,
            data.get("name", ""),
            data.get("kind", "table"),
            data.get("config"),
            request.user,
        )
        return Response(ViewSerializer(view).data, status=201)

    def partial_update(self, request, pk=None):
        view, _ = self._object(Level.MANAGE)
        data = _valid(ViewInputSerializer, request.data, partial=True)
        data.pop("board", None)
        data.pop("kind", None)
        return Response(ViewSerializer(services.update_view(view, **data)).data)

    def destroy(self, request, pk=None):
        view, _ = self._object(Level.MANAGE)
        services.delete_view(view)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ItemViewSet(BoardScoped):
    queryset = Item.objects.select_related("board__project", "group")

    def _row(self, item):
        ctx = BoardContext(item.board, self.request.membership)
        return item_rows(ctx, items_of(ctx, [item.pk], archived=item.archived_at is not None))[0]

    def retrieve(self, request, pk=None):
        item, _ = self._object()
        return Response(self._row(item))

    def partial_update(self, request, pk=None):
        """Rename, or move to another group or between two items."""
        item, _ = self._object(Level.EDIT)
        data = _valid(ItemChangeSerializer, request.data, partial=True)
        actor = _actor(request)
        if "name" in data:
            item = services.rename_item(item, data["name"], actor)
        if {"group", "before", "after"} & set(data):
            item = services.move_item(
                item, data.get("group"), data.get("before"), data.get("after"), actor
            )
        return Response(self._row(item))

    def destroy(self, request, pk=None):
        item, _ = self._object(Level.EDIT)
        services.delete_item(item)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"])
    def values(self, request, pk=None):
        """{column key: value, ...}: change those cells only."""
        item, _ = self._object(Level.EDIT)
        item = services.set_values(item, request.data, _actor(request))
        return Response(self._row(item))

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        item, _ = self._object(Level.EDIT)
        return Response(self._row(services.archive_item(item, _actor(request))))

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        item, _ = self._object(Level.EDIT)
        return Response(self._row(services.restore_item(item, _actor(request))))

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        item, _ = self._object(Level.EDIT)
        return Response(self._row(services.duplicate_item(item, _actor(request))), status=201)

    @action(detail=True, methods=["get", "post"])
    def updates(self, request, pk=None):
        if request.method == "POST":
            item, _ = self._object(Level.EDIT)
            data = _valid(UpdateInputSerializer, request.data)
            update = services.post_update(
                item, request.membership, data["body"], data.get("mentions", [])
            )
            return Response(ItemUpdateSerializer(update).data, status=201)
        item, _ = self._object()
        rows = (
            ItemUpdate.objects.in_realm(request.realm)
            .of_item(item)
            .select_related("author__user")[:200]
        )
        return Response(ItemUpdateSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        item, _ = self._object()
        rows = (
            ItemActivity.objects.in_realm(request.realm)
            .filter(item_id=item.pk)
            .select_related("actor__user", "item")[:200]
        )
        return Response(ActivitySerializer(rows, many=True).data)

    @action(detail=False, methods=["get"])
    def search(self, request):
        """Items on one board by name, for picking what a connect column links:
        ?board=&search=."""
        board, _ = board_for(request, request.query_params.get("board"))
        text = request.query_params.get("search", "").strip()[:100]
        rows = Item.objects.in_realm(request.realm).of_board(board).live()
        if text:
            rows = rows.filter(name__icontains=text)
        return Response([{"id": i.pk, "name": i.name} for i in rows.order_by("name", "id")[:50]])
