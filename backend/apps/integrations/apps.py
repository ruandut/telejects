from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    label = "integrations"

    def ready(self):
        from django.db import transaction
        from django.db.models.signals import post_save

        from apps.realms.models import Realm

        def connect_new_company(sender, instance, created, **kwargs):
            """A new company starts with every provider Telejects has an account for (0004)."""
            if not created:
                return
            from .services import ensure_default_connections

            realm = instance
            transaction.on_commit(lambda: ensure_default_connections(realm))

        post_save.connect(connect_new_company, sender=Realm, dispatch_uid="integrations-new-realm")
