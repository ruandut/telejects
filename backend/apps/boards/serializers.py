"""Boards' API shapes (0007). Items are built by `item_rows`, which the live topic uses too, so
the socket and the API always send the same thing for the same person."""

from django.db.models import Count
from rest_framework import serializers

from apps.projects.models import Project

from .context import BoardContext
from .models import Board, BoardView, Column, Group, Item, ItemActivity, ItemUpdate


class ColumnSerializer(serializers.ModelSerializer):
    class Meta:
        model = Column
        fields = ["id", "key", "title", "type", "settings", "description", "position", "width"]
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name", "colour", "position"]
        read_only_fields = fields


class ViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = BoardView
        fields = ["id", "name", "kind", "config", "position"]
        read_only_fields = fields


class ProjectRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "client", "colour"]
        read_only_fields = fields


class BoardListSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True, default=None)
    done_count = serializers.IntegerField(read_only=True, default=None)

    class Meta:
        model = Board
        fields = [
            "id",
            "name",
            "description",
            "position",
            "item_count",
            "done_count",
            "feasibility_run",
        ]
        read_only_fields = fields


def board_data(board: Board, level: str) -> dict:
    realm = board.realm_id
    return {
        "id": board.pk,
        "name": board.name,
        "description": board.description,
        "project": ProjectRefSerializer(board.project).data,
        "status_column": board.status_column,
        "due_column": board.due_column,
        "my_level": level,
        "feasibility_run": (
            {"id": board.feasibility_run_id, "name": board.feasibility_run.name}
            if board.feasibility_run_id
            else None
        ),
        "groups": GroupSerializer(Group.objects.in_realm(realm).of_board(board), many=True).data,
        "columns": ColumnSerializer(Column.objects.in_realm(realm).of_board(board), many=True).data,
        "views": ViewSerializer(BoardView.objects.in_realm(realm).of_board(board), many=True).data,
    }


def with_counts(items):
    return items.annotate(update_count=Count("updates")).order_by("position", "id")


def item_rows(ctx: BoardContext, items) -> list[dict]:
    items = list(items)
    values = ctx.full_values(items)
    return [
        {
            "id": item.pk,
            "number": item.number,
            "name": item.name,
            "group": item.group_id,
            "position": item.position,
            "values": values[item.pk],
            "done": item.done,
            "update_count": getattr(item, "update_count", 0),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "archived_at": item.archived_at,
        }
        for item in items
    ]


def items_of(ctx: BoardContext, ids=None, archived=False):
    rows = Item.objects.in_realm(ctx.realm_id).of_board(ctx.board)
    rows = rows.archived() if archived else rows.live()
    if ids is not None:
        rows = rows.filter(id__in=ids)
    return with_counts(rows)


class ItemUpdateSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ItemUpdate
        fields = ["id", "author", "author_name", "body", "mentions", "created_at", "edited_at"]
        read_only_fields = fields

    def get_author_name(self, update) -> str:
        return update.author.display_name if update.author_id else "Someone"


class ActivitySerializer(serializers.ModelSerializer):
    who = serializers.SerializerMethodField()
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = ItemActivity
        fields = [
            "id",
            "item",
            "item_name",
            "kind",
            "who",
            "automation_id",
            "column_key",
            "column_title",
            "old_text",
            "new_text",
            "at",
        ]
        read_only_fields = fields

    def get_who(self, row) -> str:
        if row.automation_id:
            return f"Automation: {row.automation_name}"
        return row.actor.display_name if row.actor_id else "Telejects"


class NewBoardSerializer(serializers.Serializer):
    project = serializers.IntegerField()
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    template = serializers.CharField(max_length=40, required=False, default="blank")
    feasibility_run = serializers.IntegerField(required=False, allow_null=True)


class BoardChangeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    status_column = serializers.CharField(max_length=40, required=False, allow_blank=True)
    due_column = serializers.CharField(max_length=40, required=False, allow_blank=True)
    position = serializers.FloatField(required=False)


class GroupInputSerializer(serializers.Serializer):
    board = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    colour = serializers.CharField(max_length=20, required=False)
    position = serializers.FloatField(required=False)
    top = serializers.BooleanField(required=False, default=False)

    def validate_colour(self, value):
        from .column_types import COLOURS

        if value not in COLOURS:
            raise serializers.ValidationError("Choose one of the colours.")
        return value


class ColumnInputSerializer(serializers.Serializer):
    board = serializers.IntegerField(required=False)
    title = serializers.CharField(max_length=80, required=False, allow_blank=True)
    type = serializers.CharField(max_length=20, required=False)
    settings = serializers.JSONField(required=False)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True)
    width = serializers.IntegerField(min_value=60, max_value=600, required=False)
    position = serializers.FloatField(required=False)
    after = serializers.CharField(max_length=40, required=False, allow_null=True)


class ViewInputSerializer(serializers.Serializer):
    board = serializers.IntegerField(required=False)
    name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    kind = serializers.CharField(max_length=10, required=False, default="table")
    config = serializers.JSONField(required=False)
    position = serializers.FloatField(required=False)


class NewItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    group = serializers.IntegerField(required=False, allow_null=True)
    values = serializers.JSONField(required=False)
    top = serializers.BooleanField(required=False, default=False)


class ItemChangeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    group = serializers.IntegerField(required=False)
    before = serializers.IntegerField(required=False, allow_null=True)
    after = serializers.IntegerField(required=False, allow_null=True)


class UpdateInputSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=10000)
    mentions = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
