from django.core.management.base import BaseCommand

from apps.users.services import create_company


class Command(BaseCommand):
    help = "Create a company and invite its first Admin by email (platform staff only)."

    def add_arguments(self, parser):
        parser.add_argument("name", help="The company's name")
        parser.add_argument("admin_email", help="Who becomes its first Admin")
        parser.add_argument("--admin-name", default="", help="Their name")

    def handle(self, *args, name, admin_email, admin_name, **options):
        membership = create_company(name, admin_email, admin_name)
        self.stdout.write(
            f"Created {membership.realm.name} (id {membership.realm_id}). "
            f"Invitation sent to {membership.user.email}; the worker delivers it."
        )
