"""Bring Rapid's price book across, keeping its ids (0006).

On Rapid:  manage.py dumpdata connect.Product connect.AccessMedium
           connect.ConnectProductDefinition connect.ConnectProduct > pricebook.json
Here:      manage.py import_rapid_pricebook pricebook.json

Running it again updates the same rows. Check each catalogue product's code in Django admin
afterwards: Link Africa's and Herotel's are taken from Rapid's names and may need mapping.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.pricebook import books


class Command(BaseCommand):
    help = "Import Rapid's price book from a dumpdata file, keeping its ids."

    def add_arguments(self, parser):
        parser.add_argument("dump", type=Path)

    def handle(self, *args, dump: Path, **options):
        counts = books.import_rapid_dump(dump.read_text())
        for name, count in counts.items():
            self.stdout.write(f"{name.replace('_', ' ')}: {count}")
