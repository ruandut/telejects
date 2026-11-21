"""Query logic for feasibility runs, their sites, checks and results."""

from django.db.models import Exists, OuterRef, Prefetch

from apps.realms.querysets import TenantQuerySet

OPEN_CHECKS = ("pending", "running")


class FeasibilityRunQuerySet(TenantQuerySet):
    def listed(self):
        return self.select_related("created_by").order_by("-created_at", "-id")

    def going(self):
        return self.filter(status__in=["queued", "running", "paused"])


class RunSiteQuerySet(TenantQuerySet):
    def of_run(self, run):
        return self.filter(run=run)

    def with_results(self):
        """Each site with its results and checks. The prefetches follow relations from sites
        already scoped to one company, so Django keeps them inside it."""
        from .models import FeasibilityResult, ProviderCheck

        return (
            self.select_related("run")
            .prefetch_related(
                Prefetch(
                    "results",
                    queryset=FeasibilityResult.objects.order_by("product_id", "variant_name", "id"),
                ),
                Prefetch("checks", queryset=ProviderCheck.objects.select_related("connection")),
            )
            .order_by("line_number", "id")
        )

    def finished(self):
        from .models import ProviderCheck

        open_check = ProviderCheck.sites.through.objects.filter(
            runsite_id=OuterRef("pk"), providercheck__status__in=OPEN_CHECKS
        )
        return self.exclude(Exists(open_check))

    def with_state(self, state: str):
        """pending: a check is still open; error: a check failed; done: all answered."""
        from .models import ProviderCheck

        through = ProviderCheck.sites.through.objects
        open_check = through.filter(
            runsite_id=OuterRef("pk"), providercheck__status__in=OPEN_CHECKS
        )
        failed = through.filter(runsite_id=OuterRef("pk"), providercheck__status="failed")
        if state == "pending":
            return self.filter(Exists(open_check))
        if state == "error":
            return self.filter(Exists(failed))
        if state == "done":
            return self.exclude(Exists(open_check)).exclude(Exists(failed))
        return self


class ProviderCheckQuerySet(TenantQuerySet):
    def open(self):
        return self.filter(status__in=OPEN_CHECKS)

    def of_run(self, run):
        return self.filter(run=run)


class FeasibilityResultQuerySet(TenantQuerySet):
    pass
