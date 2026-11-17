from django.core.management.base import BaseCommand

from apps.integrations.services import ensure_everywhere, ensure_platform_accounts, load_definitions


class Command(BaseCommand):
    help = (
        "Load the built-in connector definitions (a changed one becomes a new version), then "
        "Telejects' accounts from .env, and connect every company to them."
    )

    def handle(self, *args, **options):
        for key, version, new in load_definitions():
            self.stdout.write(f"{key} v{version}" + (" (new)" if new else " (unchanged)"))
        ready = ", ".join(a.connector_key for a in ensure_platform_accounts()) or "none"
        self.stdout.write(f"Telejects accounts configured in .env: {ready}")
        self.stdout.write(f"Connections added: {ensure_everywhere()}")
