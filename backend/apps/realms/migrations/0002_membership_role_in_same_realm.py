"""The database itself refuses a membership whose role belongs to another company.

Django can't declare a foreign key over two columns, so this adds one in SQL: a membership's
(realm_id, role_id) must match a role's (realm_id, id), which role_realm_id_pair makes unique.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("realms", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE realms_realmmembership "
                "ADD CONSTRAINT membership_role_in_same_realm "
                "FOREIGN KEY (realm_id, role_id) REFERENCES realms_role (realm_id, id) "
                "DEFERRABLE INITIALLY DEFERRED"
            ),
            reverse_sql=(
                "ALTER TABLE realms_realmmembership DROP CONSTRAINT membership_role_in_same_realm"
            ),
        )
    ]
