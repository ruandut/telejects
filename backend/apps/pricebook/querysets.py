"""Query logic for the price book."""

from django.db import models
from django.db.models import Q

from apps.realms.querysets import TenantQuerySet


class PriceBookQuerySet(models.QuerySet):
    """Platform data, kept by staff."""

    def offered_to(self, realm_id: int):
        """The books this company may quote from: offered to all, or granted to it."""
        from .models import PriceBookGrant

        granted = PriceBookGrant.objects.in_realm_id(realm_id).values("book_id")
        return self.filter(Q(available_to_all=True) | Q(id__in=granted))


class PriceBookGrantQuerySet(TenantQuerySet):
    pass


class CatalogueProductQuerySet(models.QuerySet):
    def search(self, text: str):
        return self.filter(name__icontains=text) if text else self


class AccessMediumQuerySet(models.QuerySet):
    pass


class PriceDefinitionQuerySet(models.QuerySet):
    pass


class ConnectProductQuerySet(models.QuerySet):
    def offered_to(self, realm_id: int):
        from .models import PriceBook

        return self.filter(book__in=PriceBook.objects.offered_to(realm_id))

    def search(self, text: str):
        return self.filter(name__icontains=text) if text else self
