"""Query logic for integration logs."""

from django.db.models import Q

from apps.realms.querysets import TenantQuerySet

STATUS_CLASSES = {"2xx": (200, 299), "3xx": (300, 399), "4xx": (400, 499), "5xx": (500, 599)}


class IntegrationLogQuerySet(TenantQuerySet):
    def newest(self):
        return self.order_by("-id")

    def search(self, text: str):
        """Free text over what was sent and what came back."""
        text = text.strip()[:200]
        if not text:
            return self
        return self.filter(
            Q(url__icontains=text)
            | Q(request_body__icontains=text)
            | Q(response_body__icontains=text)
            | Q(error__icontains=text)
            | Q(connection_name__icontains=text)
        )

    def with_outcome(self, outcome: str):
        if outcome == "ok":
            return self.filter(outcome="ok")
        if outcome == "error":
            return self.exclude(outcome="ok")
        return self.filter(outcome=outcome) if outcome else self

    def with_status(self, status: str):
        if status in STATUS_CLASSES:
            low, high = STATUS_CLASSES[status]
            return self.filter(status_code__gte=low, status_code__lte=high)
        if status == "none":
            return self.filter(status_code=None)
        if status.isdigit():
            return self.filter(status_code=int(status))
        return self


class LogRetentionQuerySet(TenantQuerySet):
    pass
