from apps.realms.querysets import TenantQuerySet


class NotificationQuerySet(TenantQuerySet):
    def for_membership(self, membership):
        return self.filter(recipient_id=membership.pk)

    def unread(self):
        return self.filter(read_at__isnull=True)
