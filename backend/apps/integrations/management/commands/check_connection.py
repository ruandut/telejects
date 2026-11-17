from django.core.management.base import BaseCommand, CommandError

from apps.integrations import services
from apps.integrations.models import Connection


class Command(BaseCommand):
    help = "Test one connection against its provider, live, and print the outcome."

    def add_arguments(self, parser):
        parser.add_argument("realm_id", type=int)
        parser.add_argument("connection_id", type=int)

    def handle(self, realm_id, connection_id, **options):
        connection = Connection.objects.in_realm_id(realm_id).by_id(connection_id)
        if connection is None:
            raise CommandError("No such connection in that company.")
        ok = services.test_connection(connection, "manual")
        connection.refresh_from_db()
        self.stdout.write(f"{connection.name}: {connection.get_health_display()}")
        if not ok:
            self.stdout.write(connection.health_error)
