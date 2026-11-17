"""Query logic for connectors, connections and provider products."""

from django.db import models
from django.db.models import Max

from apps.realms.querysets import TenantQuerySet


class ConnectorDefinitionQuerySet(models.QuerySet):
    """The platform's connector catalogue: the same for every company, read-only to them."""

    def published(self):
        return self.filter(published=True)

    def latest(self):
        """The newest published version of each connector."""
        newest = self.published().values("key").annotate(top=Max("version"))
        pairs = models.Q()
        for row in newest:
            pairs |= models.Q(key=row["key"], version=row["top"])
        return self.published().filter(pairs).order_by("key") if newest else self.none()

    def latest_for(self, key: str):
        return self.published().filter(key=key).order_by("-version").first()


class ConnectionQuerySet(TenantQuerySet):
    def enabled(self):
        return self.filter(enabled=True)

    def listed(self):
        return self.order_by("name", "id")


class ProviderProductQuerySet(TenantQuerySet):
    def current(self):
        """Products the provider still offers: the only ones a new run may use."""
        return self.filter(retired_at=None, connection__enabled=True)

    def listed(self):
        return self.select_related("connection").order_by("connection__name", "name", "id")


class SyncRunQuerySet(TenantQuerySet):
    def recent(self):
        return self.order_by("-started_at", "-id")

    def last_of(self, connection, kind: str):
        return self.filter(connection=connection, kind=kind).recent().first()
