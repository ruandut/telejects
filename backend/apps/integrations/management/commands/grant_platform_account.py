from django.core.management.base import BaseCommand, CommandError

from apps.integrations import services
from apps.integrations.models import PlatformAccount
from apps.realms.models import Realm


class Command(BaseCommand):
    help = "Let a company use one of Telejects' provider accounts (or --withdraw it)."

    def add_arguments(self, parser):
        parser.add_argument("realm_id", type=int)
        parser.add_argument("account_id", type=int)
        parser.add_argument("--withdraw", action="store_true")

    def handle(self, realm_id, account_id, withdraw, **options):
        realm = Realm.objects.filter(pk=realm_id).first()
        account = PlatformAccount.objects.filter(pk=account_id).first()
        if realm is None or account is None:
            raise CommandError("No such company or platform account.")
        if withdraw:
            count = services.withdraw_platform_account(realm, account)
            self.stdout.write(f"Withdrew {account} from {realm}; {count} connection(s) turned off.")
        else:
            services.grant_platform_account(realm, account)
            self.stdout.write(f"{realm} may now use {account}.")
