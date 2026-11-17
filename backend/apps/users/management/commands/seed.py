import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.realms import services
from apps.realms.access_control import ADMIN
from apps.realms.models import Realm

COMPANY_NAME = "Telejects Demo"


class Command(BaseCommand):
    help = "Local development only: the sign-in from .env, as Admin of a first company."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed is for local development (DEBUG=true) only.")
        email = os.environ.get("DEV_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("DEV_ADMIN_PASSWORD", "")
        if not email or not password:
            raise CommandError("DEV_ADMIN_EMAIL and DEV_ADMIN_PASSWORD must be set in .env.")

        users = get_user_model().objects
        user = users.filter(email=email).first()
        if user is None:
            user = users.create_superuser(email=email, password=password)
            self.stdout.write(f"Created {email} (password: DEV_ADMIN_PASSWORD in .env)")

        realm = Realm.objects.filter(name=COMPANY_NAME).first()
        if realm is None:
            realm = services.create_realm(COMPANY_NAME)
            self.stdout.write(f"Created company {COMPANY_NAME}")
        services.ensure_system_roles(realm)
        services.add_member(realm, user, ADMIN)
        self.stdout.write("Seed done.")
