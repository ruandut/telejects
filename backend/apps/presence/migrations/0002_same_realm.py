"""The database refuses presence on another company's board."""

from django.db import migrations

from apps.core.db import same_realm


class Migration(migrations.Migration):
    dependencies = [("presence", "0001_initial"), ("boards", "0003_same_realm")]

    operations = [
        same_realm("presence_boardpresence", "board_id", "boards_board", "presence_board_in_same_realm"),
    ]
