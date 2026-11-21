"""The database refuses a dashboard on another company's project."""

from django.db import migrations

from apps.core.db import same_realm


class Migration(migrations.Migration):
    dependencies = [("analytics", "0002_initial"), ("projects", "0002_same_realm")]

    operations = [
        same_realm("analytics_dashboard", "project_id", "projects_project", "dashboard_project_in_same_realm"),
    ]
