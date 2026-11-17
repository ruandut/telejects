"""The built-in Field technician role is gone. Anyone who had it becomes a Viewer (it gave no
permissions either), and Viewer moves up to take its place in the list."""

from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("realms", "Role")
    RealmMembership = apps.get_model("realms", "RealmMembership")
    for old in Role.objects.filter(is_system=True, key="field_technician"):
        viewer = Role.objects.get(realm_id=old.realm_id, is_system=True, key="viewer")
        RealmMembership.objects.filter(realm_id=old.realm_id, role_id=old.id).update(
            role_id=viewer.id
        )
        old.delete()
    Role.objects.filter(is_system=True, key="viewer").update(position=2)


class Migration(migrations.Migration):
    dependencies = [("realms", "0002_membership_role_in_same_realm")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
