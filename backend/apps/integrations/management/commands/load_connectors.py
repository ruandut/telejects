from django.core.management.base import BaseCommand

from apps.integrations.services import load_definitions


class Command(BaseCommand):
    help = "Load the built-in connector definitions. A changed one becomes a new version."

    def handle(self, *args, **options):
        for key, version, new in load_definitions():
            self.stdout.write(f"{key} v{version}" + (" (new)" if new else " (unchanged)"))
