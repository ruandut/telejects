"""Multi-tenancy. A realm is a company using the platform; it runs many projects.

Every domain row belongs to exactly one realm (TenantModel), and every API request works inside
one realm the user is an active member of (permissions.py). People join a realm through a
membership, which gives them one of the realm's roles. What a role allows is a set of permission
codes (access_control.py).
"""

from django.conf import settings
from django.db import models

from . import access_control
from .querysets import RealmMembershipQuerySet, RealmQuerySet, RoleQuerySet, TenantQuerySet


class Realm(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = RealmQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class TenantModel(models.Model):
    """Base for every row that belongs to a realm. Deleting the realm deletes the row."""

    realm = models.ForeignKey(Realm, on_delete=models.CASCADE, related_name="+")

    objects = TenantQuerySet.as_manager()

    class Meta:
        abstract = True


class Role(TenantModel):
    """One of a company's roles. Every company has the built-in ones (`is_system`), whose
    permissions come from access_control.SYSTEM_ROLES. Custom roles (later) keep their own
    `permissions` list here."""

    key = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.JSONField(default=list, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    objects = RoleQuerySet.as_manager()

    class Meta:
        ordering = ["position", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["realm", "key"], name="role_key_unique_in_realm"),
            # Lets a membership's (realm, role) point at this pair, so the database itself
            # refuses a role from another company (see the realms migrations).
            models.UniqueConstraint(fields=["realm", "id"], name="role_realm_id_pair"),
        ]

    def __str__(self):
        return self.name

    @property
    def permission_set(self) -> frozenset[str]:
        if self.is_system:
            return access_control.system_role_permissions(self.key)
        return frozenset(self.permissions) & frozenset(access_control.PERMISSIONS)

    @property
    def is_admin(self) -> bool:
        return self.is_system and self.key == access_control.ADMIN


class RealmMembership(models.Model):
    """A person in a company: their name there, their role and whether they have access."""

    class Status(models.TextChoices):
        INVITED = "invited", "Invited"  # added, hasn't confirmed their account yet
        ACTIVE = "active", "Active"
        REMOVED = "removed", "Removed"  # kept so past work stays attributable

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="realm_memberships"
    )
    realm = models.ForeignKey(Realm, on_delete=models.CASCADE, related_name="memberships")
    # Always one of this realm's roles; a composite foreign key enforces it in the database.
    # RESTRICT: a role in use can't be deleted on its own, but deleting the company takes both.
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="memberships")
    # Only active memberships give access. Only apps/users/services.py changes these fields.
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # The person's name in this realm. Kept here, not on the account, so one realm's admins
    # can't change what another realm sees.
    name = models.CharField(max_length=150, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    objects = RealmMembershipQuerySet.as_manager()

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "realm"], name="one_membership_per_realm")
        ]

    def __str__(self):
        return f"{self.user} in {self.realm} ({self.role})"

    @property
    def permissions(self) -> frozenset[str]:
        return self.role.permission_set

    def has_perm(self, code: str, project=None) -> bool:
        """Whether this person may do `code` in this company.

        `project` is for per-project access (a later spec: guests and project roles). Until
        then it is always None and the company-wide role decides.
        """
        if code not in access_control.PERMISSIONS:
            raise KeyError(f"Unknown permission {code!r}; add it to access_control.PERMISSIONS")
        return self.is_active and code in self.permissions

    @property
    def is_admin(self) -> bool:
        return self.role.is_admin

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def display_name(self) -> str:
        return self.name or self.user.display_name
