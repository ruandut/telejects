"""User management for a company: invitations.

A "user" in this app is a company membership (apps/realms/models.py): the person's name, role
and status in one company. The account behind it (apps/accounts) only carries the email and
password.
"""

from django.db import models

from apps.realms.models import RealmMembership, TenantModel

from .querysets import InvitationQuerySet


class Invitation(TenantModel):
    """The link emailed to someone who was added. One per invited membership at a time.

    Only a hash of the token is stored, and it is filled in by the task that sends the email,
    so the token itself exists only in that email.
    """

    membership = models.OneToOneField(
        RealmMembership, on_delete=models.CASCADE, related_name="invitation"
    )
    token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    objects = InvitationQuerySet.as_manager()

    def __str__(self):
        return f"Invitation for {self.membership}"
