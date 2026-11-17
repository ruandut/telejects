import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Local development only: the sign-in from .env. Safe to re-run."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed is for local development (DEBUG=true) only.")
        email = os.environ.get("DEV_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("DEV_ADMIN_PASSWORD", "")
        if not email or not password:
            raise CommandError("DEV_ADMIN_EMAIL and DEV_ADMIN_PASSWORD must be set in .env.")

        users = get_user_model().objects
        if not users.filter(email=email).exists():
            users.create_superuser(email=email, password=password)
            self.stdout.write(f"Created {email} (password: DEV_ADMIN_PASSWORD in .env)")
        self.stdout.write("Seed done.")
