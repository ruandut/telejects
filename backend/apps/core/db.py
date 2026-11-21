"""Database helpers shared by the apps' migrations."""

from django.db import migrations


def same_realm(table: str, column: str, target: str, name: str) -> migrations.RunSQL:
    """The database itself refuses a row whose `column` points at a `target` row of another
    company. Django can't declare a foreign key over two columns, so this adds one in SQL:
    (realm_id, column) must match the target's (realm_id, id), which the target's
    `<model>_realm_id_pair` unique constraint makes possible. A NULL column is allowed."""
    return migrations.RunSQL(
        sql=(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY (realm_id, {column}) REFERENCES {target} (realm_id, id) "
            "DEFERRABLE INITIALLY DEFERRED"
        ),
        reverse_sql=f"ALTER TABLE {table} DROP CONSTRAINT {name}",
    )
