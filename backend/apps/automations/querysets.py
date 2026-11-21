from apps.boards.querysets import BoardChildQuerySet
from apps.realms.querysets import TenantQuerySet


class AutomationQuerySet(BoardChildQuerySet):
    def enabled(self):
        return self.filter(enabled=True)

    def triggered_by(self, *kinds):
        return self.filter(trigger__type__in=kinds)


class RunQuerySet(TenantQuerySet):
    def of_automation(self, automation):
        return self.filter(automation_id=automation.pk)

    def due(self, now):
        return self.filter(status="scheduled", due_at__lte=now)
