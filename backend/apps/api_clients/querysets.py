"""Query logic for API clients."""

from apps.realms.querysets import TenantQuerySet


class ApiClientQuerySet(TenantQuerySet):
    def active(self):
        return self.filter(revoked_at=None, application__isnull=False)

    def listed(self):
        return self.select_related("created_by").order_by("-revoked_at", "name", "id")

    def for_token(self, application_id: int):
        """The client a token belongs to, whichever company: the token is the only thing that
        names it. A request then works in that client's company alone."""
        return (
            self.across_realms()
            .active()
            .filter(application_id=application_id)
            .select_related("realm")
            .first()
        )
