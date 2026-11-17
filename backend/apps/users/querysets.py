"""Query logic for invitations. The people themselves are RealmMemberships: see
RealmMembershipQuerySet in apps/realms."""

from apps.realms.querysets import TenantQuerySet


class InvitationQuerySet(TenantQuerySet):
    def for_membership(self, membership):
        return self.filter(membership=membership)

    def by_token_hash(self, token_hash: str):
        """The invitation a link's token belongs to, in whichever company it is.

        Across companies by design: the person holding the link isn't signed in, and the token
        is the only thing that names the company. It reveals only what the link is for.
        """
        if not token_hash:
            return None
        return (
            self.across_realms()
            .select_related("membership__user", "membership__realm")
            .filter(token_hash=token_hash)
            .first()
        )

    def unsent(self, pk):
        return self.select_related("membership__user", "membership__realm").filter(
            pk=pk, used_at=None
        )
