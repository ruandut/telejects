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
    def offered_to(self, realm_id: int):
        """What a company may read: definitions of the connect products it is offered."""
        from .models import ConnectProduct

        offered = ConnectProduct.objects.offered_to(realm_id).values("id")
        return self.filter(connect_products__in=offered).distinct()

    def search(self, text: str):
        """Rapid's search: the definition's, its product's or its access medium's name."""
        if not text:
            return self
        return self.filter(
            Q(name__icontains=text)
            | Q(product__name__icontains=text)
            | Q(access_medium__name__icontains=text)
        )

    def filtered(self, *, provider=None, medium=None, product=None):
        """Rapid's filters. A provider or product that isn't a number matches nothing."""
        found = self
        for field, value in (("provider", provider), ("product", product)):
            if value not in (None, ""):
                found = found.filter(**{field: value}) if str(value).isdigit() else found.none()
        if medium:
            found = found.filter(medium=medium)
        return found


class ConnectProductQuerySet(models.QuerySet):
    def offered_to(self, realm_id: int):
        from .models import PriceBook

        return self.filter(book__in=PriceBook.objects.offered_to(realm_id))

    def search(self, text: str):
        return self.filter(name__icontains=text) if text else self
