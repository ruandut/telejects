"""The database refuses an automation on another company's board."""

from django.db import migrations

from apps.core.db import same_realm


class Migration(migrations.Migration):
    dependencies = [("automations", "0002_initial"), ("boards", "0003_same_realm")]

    operations = [
        same_realm("automations_automation", "board_id", "boards_board", "automation_board_in_same_realm"),
    ]
