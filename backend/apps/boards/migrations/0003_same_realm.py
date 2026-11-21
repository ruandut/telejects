"""The database refuses a board, group, column, item or update pointing into another company."""

from django.db import migrations

from apps.core.db import same_realm


class Migration(migrations.Migration):
    dependencies = [("boards", "0002_initial"), ("projects", "0002_same_realm")]

    operations = [
        same_realm("boards_board", "project_id", "projects_project", "board_project_in_same_realm"),
        same_realm("boards_group", "board_id", "boards_board", "group_board_in_same_realm"),
        same_realm("boards_column", "board_id", "boards_board", "column_board_in_same_realm"),
        same_realm("boards_boardview", "board_id", "boards_board", "view_board_in_same_realm"),
        same_realm("boards_item", "board_id", "boards_board", "item_board_in_same_realm"),
        same_realm("boards_item", "group_id", "boards_group", "item_group_in_same_realm"),
        same_realm("boards_itemupdate", "item_id", "boards_item", "update_item_in_same_realm"),
        same_realm("boards_itemactivity", "item_id", "boards_item", "activity_item_in_same_realm"),
    ]
