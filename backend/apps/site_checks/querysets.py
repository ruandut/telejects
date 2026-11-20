"""Query logic for one-site checks."""

from apps.realms.querysets import TenantQuerySet


class SiteCheckQuerySet(TenantQuerySet):
    def recent(self):
        return self.order_by("-id")


class SiteCheckCallQuerySet(TenantQuerySet):
    def of_check(self, site_check):
        return self.filter(site_check=site_check)

    def open(self):
        from .models import SiteCheckCall

        return self.filter(status__in=[SiteCheckCall.Status.PENDING, SiteCheckCall.Status.RUNNING])


class SiteCheckResultQuerySet(TenantQuerySet):
    def of_check(self, site_check):
        return self.filter(site_check=site_check)

    def feasible(self):
        """What Rapid called feasible: available, or, for the Vodacom access media where
        Rapid counts coverage alone, coverage only."""
        from django.db.models import Q

        from apps.integrations.canonical import Status

        return self.filter(
            Q(status=Status.AVAILABLE)
            | Q(
                status=Status.COVERAGE_ONLY,
                connector_key="vodacom",
                variant_code__in=VODACOM_COVERAGE_COUNTS,
            )
        )


# Vodacom access medium ids where Rapid counts coverage alone as feasible
# (connect/interfaces/feasibilities/vodacom.py, TEMP_VODACOM_HACK_FIX_ITEMS).
VODACOM_COVERAGE_COUNTS = [str(i) for i in (1, 3, 4, 5, 6, 7, 31, 32, 33, 34, 43, 45, 95, 97)]
