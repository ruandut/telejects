"""The database refuses sharing a project with a row of another company."""

from django.db import migrations

from apps.core.db import same_realm


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]

    operations = [
        same_realm("projects_projectmember", "project_id", "projects_project", "project_member_in_same_realm"),
    ]
